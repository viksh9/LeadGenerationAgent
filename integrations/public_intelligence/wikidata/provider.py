"""Wikidata provider → normalized PublicCompanyFacts.

Used for company IDENTITY verification only (wikidata_id, official website, country,
industry). People/employment are intentionally not asserted from Wikidata (§13).
Nothing is fabricated — absent fields stay None.
"""

from __future__ import annotations

from typing import Optional

import httpx

from integrations.public_intelligence.base import PublicIntelligenceProvider
from integrations.public_intelligence.matching import normalize_company
from integrations.public_intelligence.models import CompanyContext, PublicCompanyFacts
from integrations.public_intelligence.wikidata.client import WikidataClient

_ENTITY_URL = "https://www.wikidata.org/wiki/"


def _val(binding: dict, key: str) -> Optional[str]:
    node = binding.get(key)
    return node.get("value") if isinstance(node, dict) else None


class WikidataProvider(PublicIntelligenceProvider):
    name = "wikidata"
    source_label = "Wikidata"
    source_type = "wikidata_entity"

    def __init__(self, *, http: httpx.Client | None = None, sleep=None) -> None:
        self._client = WikidataClient(http=http, sleep=sleep)

    def health_check(self):
        from collectors.base import HealthStatus
        from integrations.public_intelligence.base import ProviderRateLimited, ProviderUnavailable
        try:
            self._client.find_company("Wikidata")   # trivial real query
            return HealthStatus.HEALTHY, "Wikidata SPARQL reachable."
        except ProviderRateLimited:
            return HealthStatus.RATE_LIMITED, "Wikidata rate limit reached."
        except ProviderUnavailable as exc:
            return HealthStatus.UNAVAILABLE, str(exc)

    def discover_company(self, ctx: CompanyContext) -> Optional[PublicCompanyFacts]:
        binding = self._client.find_company(ctx.company_name)
        if not binding:
            return None
        item_uri = _val(binding, "item") or ""
        qid = item_uri.rsplit("/", 1)[-1] if item_uri else None
        label = _val(binding, "itemLabel")
        # Guard against a coincidental label collision: require a normalized-name match.
        if label and normalize_company(label) and normalize_company(ctx.company_name):
            if normalize_company(label) != normalize_company(ctx.company_name) and \
               normalize_company(ctx.company_name) not in normalize_company(label):
                return None
        return PublicCompanyFacts(
            website=_val(binding, "website"),
            country=_val(binding, "countryLabel"),
            industry=_val(binding, "industryLabel"),
            aliases=[label] if (label and label != ctx.company_name) else [],
            wikidata_id=qid,
            source=self.name, source_label=self.source_label,
            source_url=(f"{_ENTITY_URL}{qid}" if qid else item_uri or None),
        )
