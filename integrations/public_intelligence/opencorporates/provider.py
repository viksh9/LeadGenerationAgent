"""OpenCorporates provider → legal-entity verification facts (Prompt 47).

Supporting legal evidence only — never overrides stronger official-company data.
Registered address is kept DISTINCT from the operating address; legal officers are
kept separate from sales/technical POCs. Nothing is fabricated: NO_MATCH and absent
fields are surfaced honestly; a single exact match is only VERIFIED with corroboration.
"""

from __future__ import annotations

import logging
from typing import Optional

import httpx

from integrations.public_intelligence.base import (
    ProviderAuthError,
    ProviderRateLimited,
    ProviderUnavailable,
    PublicIntelligenceProvider,
)
from integrations.public_intelligence.models import (
    CompanyContext,
    CompanyFieldEvidenceRecord,
    CompanyLocationRecord,
    PublicCompanyFacts,
)
from integrations.public_intelligence.opencorporates.client import OpenCorporatesClient
from integrations.public_intelligence.opencorporates.exceptions import (
    OpenCorporatesAuthError,
    OpenCorporatesNotConfigured,
    OpenCorporatesRateLimited,
    OpenCorporatesUnavailable,
)
from integrations.public_intelligence.opencorporates.mapper import parse_company_detail, parse_search
from integrations.public_intelligence.opencorporates.matching import (
    NO_MATCH,
    classify_india_entity,
    match_entity,
)
from integrations.public_intelligence.opencorporates.models import OCCompany

logger = logging.getLogger("integrations.public_intelligence")

_PRIORITY = 5   # §1: OpenCorporates ranks below official-company sources
_FIELD_TRUST = {"legal_name": 90, "company_number": 95, "jurisdiction_code": 90,
                "company_status": 80, "registered_address": 85, "registry_url": 90,
                "opencorporates_url": 90, "incorporation_date": 85}


def _status(oc: OCCompany) -> str:
    cur = (oc.current_status or "").lower()
    if oc.dissolution_date or "dissolv" in cur:
        return "DISSOLVED"
    if oc.inactive is True or any(k in cur for k in ("inactive", "struck", "closed", "defunct")):
        return "INACTIVE"
    if any(k in cur for k in ("active", "live", "registered", "in existence")):
        return "ACTIVE"
    return "UNKNOWN"


class OpenCorporatesProvider(PublicIntelligenceProvider):
    name = "opencorporates"
    source_label = "OpenCorporates"
    source_type = "company_registry"

    def __init__(self, *, client: Optional[OpenCorporatesClient] = None,
                 http: httpx.Client | None = None) -> None:
        self._client = client or OpenCorporatesClient(http=http)

    def discover_company(self, ctx: CompanyContext) -> Optional[PublicCompanyFacts]:
        try:
            raw = self._client.search_companies(ctx.company_name, per_page=10)
        except OpenCorporatesNotConfigured:
            return None
        except OpenCorporatesRateLimited as exc:
            raise ProviderRateLimited(str(exc)) from exc
        except OpenCorporatesAuthError as exc:
            raise ProviderAuthError(str(exc)) from exc
        except OpenCorporatesUnavailable as exc:
            raise ProviderUnavailable(str(exc)) from exc

        candidates = parse_search(raw or {}).companies
        best, match_status = match_entity(company_name=ctx.company_name, candidates=candidates,
                                          prefer_india=True)
        logger.info("opencorporates.match company_id=%s candidates=%s match_status=%s",
                    ctx.company_id, len(candidates), match_status)
        if best is None or match_status == NO_MATCH:
            logger.info("opencorporates.no_match company_id=%s", ctx.company_id)
            return PublicCompanyFacts(source=self.name, source_label=self.source_label,
                                      match_status=NO_MATCH)

        # Fetch full detail (officers, complete registered address) for the matched entity.
        if best.jurisdiction_code and best.company_number:
            try:
                detail = parse_company_detail(
                    self._client.get_company(best.jurisdiction_code, best.company_number) or {})
                if detail is not None:
                    best = detail
            except (OpenCorporatesRateLimited, OpenCorporatesAuthError, OpenCorporatesUnavailable):
                pass   # keep the search-result data; never fail the whole match

        return self._to_facts(best, match_status)

    def _to_facts(self, oc: OCCompany, match_status: str) -> PublicCompanyFacts:
        status = _status(oc)
        facts = PublicCompanyFacts(
            source=self.name, source_label=self.source_label, source_url=oc.opencorporates_url,
            legal_name=oc.legal_name, company_number=oc.company_number,
            jurisdiction_code=oc.jurisdiction_code, company_status=status,
            incorporation_date=oc.incorporation_date, registry_url=oc.registry_url,
            opencorporates_url=oc.opencorporates_url, opencorporates_id=oc.opencorporates_id,
            match_status=match_status,
            india_entity_type=classify_india_entity(oc, india_presence=False),
            industry=oc.industry_codes[0] if oc.industry_codes else None,
            officers=[{"name": o.name, "position": o.position, "start_date": o.start_date,
                       "end_date": o.end_date, "source": self.source_label,
                       "source_url": oc.opencorporates_url} for o in oc.officers if o.name],
        )
        addr = oc.registered_address
        if addr.any():
            full = addr.in_full or ", ".join(p for p in (addr.line_1, addr.city, addr.region,
                                                         addr.postal_code, addr.country) if p)
            facts.registered_location = CompanyLocationRecord(
                address_line_1=addr.line_1, city=addr.city, state_or_region=addr.region,
                postal_code=addr.postal_code, country=addr.country, full_address=full,
                location_type="REGISTERED_OFFICE", is_headquarters=False,
                source=self.source_label, source_url=oc.registry_url or oc.opencorporates_url)

        # Field-level evidence (§14/§17) — each legal field, sourced to OpenCorporates.
        src_url = oc.registry_url or oc.opencorporates_url
        ev = facts.field_evidence
        for fld, val in (("legal_name", oc.legal_name), ("company_number", oc.company_number),
                         ("jurisdiction_code", oc.jurisdiction_code), ("company_status", status),
                         ("incorporation_date", oc.incorporation_date),
                         ("registry_url", oc.registry_url), ("opencorporates_url", oc.opencorporates_url)):
            if val:
                ev.append(CompanyFieldEvidenceRecord(
                    field=fld, value=val, source=self.source_label, source_type=self.source_type,
                    source_url=src_url, evidence_text=(oc.publisher or None),
                    source_priority=_PRIORITY, trust_score=_FIELD_TRUST.get(fld, 80)))
        if facts.registered_location and facts.registered_location.full_address:
            ev.append(CompanyFieldEvidenceRecord(
                field="registered_address", value=facts.registered_location.full_address,
                source=self.source_label, source_type=self.source_type, source_url=src_url,
                evidence_text=facts.registered_location.full_address, source_priority=_PRIORITY,
                trust_score=_FIELD_TRUST["registered_address"]))
        return facts

    def health_check(self):
        from collectors.base import HealthStatus
        if not self._client.is_configured:
            return HealthStatus.NOT_CONFIGURED, "No OpenCorporates API token configured."
        try:
            self._client.search_companies("Infosys", per_page=1)   # cheap real query
            return HealthStatus.HEALTHY, "OpenCorporates reachable and authenticated."
        except OpenCorporatesAuthError:
            return HealthStatus.AUTHENTICATION_FAILED, "OpenCorporates rejected the API token."
        except OpenCorporatesRateLimited:
            return HealthStatus.RATE_LIMITED, "OpenCorporates rate limit reached."
        except (OpenCorporatesUnavailable, OpenCorporatesNotConfigured):
            return HealthStatus.UNAVAILABLE, "OpenCorporates request failed."
