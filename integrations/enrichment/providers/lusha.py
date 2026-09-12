"""Lusha provider — person + company enrichment (§5).

Current documented API (api.lusha.com, header `api_key`):
    GET /v2/person    — person enrichment (name + company/domain)
    GET /v2/company   — company enrichment (domain / name)
Only fields the account is entitled to are returned. Exact request/response per
Lusha's live V2 contract — REQUIRES_REVIEW.
"""

from __future__ import annotations

from typing import Any, Optional

import httpx

from collectors.base import HealthStatus
from config import get_settings
from integrations.enrichment.base import (
    CompanyEnrichment,
    EmailResult,
    EnrichedPerson,
    EnrichmentAuthError,
    EnrichmentForbidden,
    EnrichmentNotConfigured,
    EnrichmentProvider,
    EnrichmentRateLimited,
    EnrichmentUnavailable,
    PhoneResult,
    ProviderCapabilities,
)
from integrations.enrichment.http import EnrichmentHttpClient


def _first(v: Any, key: Optional[str] = None) -> Optional[str]:
    if isinstance(v, list) and v:
        v = v[0]
    if isinstance(v, dict) and key:
        v = v.get(key)
    return v if isinstance(v, str) and v.strip() else None


class LushaProvider(EnrichmentProvider):
    name = "lusha"
    source_label = "Lusha"
    capabilities = ProviderCapabilities(person_enrichment=True, company_enrichment=True)

    def __init__(self, *, http: httpx.Client | None = None, sleep=None) -> None:
        s = get_settings()
        self._key = s.lusha_api_key
        self._client = EnrichmentHttpClient(
            base_url=s.lusha_base_url, auth_header="api_key", auth_value=self._key or "",
            provider="lusha", requests_per_minute=s.enrichment_rate_per_minute,
            timeout_seconds=s.enrichment_timeout_seconds, http=http, **({"sleep": sleep} if sleep else {}))

    def is_configured(self) -> bool:
        return bool(self._key)

    def _get(self, path: str, params: dict):
        if not self._key:
            raise EnrichmentNotConfigured("LUSHA_API_KEY is not configured.")
        return self._client.request("GET", path, params=params)

    def enrich_person(self, *, full_name: Optional[str] = None, linkedin_url: Optional[str] = None,
                      company_name: Optional[str] = None, domain: Optional[str] = None) -> Optional[EnrichedPerson]:
        if not full_name and not linkedin_url:
            return None
        params: dict = {}
        if full_name:
            parts = full_name.split()
            params["firstName"], params["lastName"] = parts[0], parts[-1]
        if linkedin_url:
            params["linkedinUrl"] = linkedin_url
        if domain:
            params["companyDomain"] = domain
        elif company_name:
            params["companyName"] = company_name
        raw = self._get("/v2/person", params) or {}
        contact = raw.get("data") if isinstance(raw.get("data"), dict) else raw
        contact = contact.get("contact", contact) if isinstance(contact, dict) else {}
        if not isinstance(contact, dict) or not contact:
            return None
        email = _first(contact.get("emailAddresses"), "email") or _first(contact.get("emailAddresses"))
        phone = _first(contact.get("phoneNumbers"), "number") or _first(contact.get("phoneNumbers"))
        name = contact.get("fullName") or " ".join(p for p in (contact.get("firstName"), contact.get("lastName")) if p) or full_name
        return EnrichedPerson(
            full_name=name, job_title=contact.get("jobTitle") or contact.get("title"),
            company_name=company_name, company_domain=domain,
            linkedin_url=_first(contact.get("socialLinks"), "url") or linkedin_url,
            provider_person_id=str(contact.get("id")) if contact.get("id") is not None else None,
            work_email=EmailResult(email=email, verification_status="UNVERIFIED", source=self.source_label)
            if email else None,
            phone=PhoneResult(number=phone, phone_type="UNKNOWN", source=self.source_label) if phone else None,
            source=self.name, source_label=self.source_label)

    def get_company_enrichment(self, *, company_name: str, domain: Optional[str] = None) -> Optional[CompanyEnrichment]:
        params = {"domain": domain} if domain else {"company": company_name}
        raw = self._get("/v2/company", params) or {}
        c = raw.get("data") if isinstance(raw.get("data"), dict) else raw
        if not isinstance(c, dict) or not c:
            return None
        return CompanyEnrichment(name=c.get("name"), domain=c.get("domain") or c.get("website"),
                                 linkedin_url=_first(c.get("socialLinks"), "url"),
                                 industry=c.get("industry"), country=c.get("country"),
                                 provider_company_id=str(c.get("id")) if c.get("id") is not None else None,
                                 source=self.source_label)

    def health_check(self) -> tuple[HealthStatus, str]:
        if not self._key:
            return HealthStatus.NOT_CONFIGURED, "No Lusha API key configured."
        try:
            self._get("/v2/company", {"domain": "lusha.com"})
            return HealthStatus.HEALTHY, "Lusha reachable and authenticated."
        except EnrichmentAuthError:
            return HealthStatus.AUTHENTICATION_FAILED, "Lusha rejected the API key."
        except EnrichmentForbidden:
            return HealthStatus.RESTRICTED, "Lusha access forbidden."
        except EnrichmentRateLimited:
            return HealthStatus.RATE_LIMITED, "Lusha rate limit reached."
        except EnrichmentUnavailable:
            return HealthStatus.UNAVAILABLE, "Lusha request failed."
