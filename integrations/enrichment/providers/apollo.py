"""Apollo provider — people search + enrichment + organization enrichment (§6).

Current documented API (api.apollo.io, header `X-Api-Key`):
    POST /v1/mixed_people/search   — candidate discovery (email/phone often locked)
    POST /v1/people/match          — enrich a selected person (contact details)
    GET  /v1/organizations/enrich  — company enrichment
People Search is for discovery; People Match (enrichment) is used only after selecting
a candidate, to avoid unnecessary credits. Exact fields per Apollo's live docs —
REQUIRES_REVIEW.
"""

from __future__ import annotations

from typing import Optional

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


def _org(node: dict) -> tuple[Optional[str], Optional[str], Optional[str]]:
    org = node.get("organization") or {}
    return org.get("name"), (org.get("primary_domain") or org.get("website_url")), org.get("id")


class ApolloProvider(EnrichmentProvider):
    name = "apollo"
    source_label = "Apollo"
    capabilities = ProviderCapabilities(person_search=True, person_enrichment=True,
                                        company_enrichment=True)

    def __init__(self, *, http: httpx.Client | None = None, sleep=None) -> None:
        s = get_settings()
        self._key = s.apollo_api_key
        self._client = EnrichmentHttpClient(
            base_url=s.apollo_base_url, auth_header="X-Api-Key", auth_value=self._key or "",
            provider="apollo", requests_per_minute=s.enrichment_rate_per_minute,
            timeout_seconds=s.enrichment_timeout_seconds, http=http, **({"sleep": sleep} if sleep else {}))

    def is_configured(self) -> bool:
        return bool(self._key)

    def _post(self, path: str, body: dict):
        if not self._key:
            raise EnrichmentNotConfigured("APOLLO_API_KEY is not configured.")
        return self._client.request("POST", path, json=body)

    def _person(self, node: dict) -> EnrichedPerson:
        oname, odomain, oid = _org(node)
        emails = node.get("email")
        phones = node.get("phone_numbers") or []
        return EnrichedPerson(
            full_name=node.get("name"), first_name=node.get("first_name"), last_name=node.get("last_name"),
            job_title=node.get("title"), seniority=node.get("seniority"),
            company_name=oname, company_domain=odomain, provider_company_id=oid,
            linkedin_url=node.get("linkedin_url"), location=node.get("city") or node.get("country"),
            provider_person_id=node.get("id"),
            work_email=EmailResult(email=emails, verification_status="UNVERIFIED", source=self.source_label,
                                   source_url=node.get("linkedin_url")) if emails else None,
            phone=PhoneResult(number=(phones[0].get("sanitized_number") if isinstance(phones[0], dict) else phones[0]),
                              phone_type="UNKNOWN", source=self.source_label) if phones else None,
            source=self.name, source_label=self.source_label, source_url=node.get("linkedin_url"))

    def search_people(self, *, company_name: str, titles: list[str],
                      domain: Optional[str] = None, location: Optional[str] = None) -> list[EnrichedPerson]:
        body: dict = {"page": 1, "per_page": 10, "person_titles": titles or []}
        if domain:
            body["q_organization_domains"] = [domain]
        else:
            body["q_organization_name"] = company_name
        if location:
            body["person_locations"] = [location]
        data = self._post("/v1/mixed_people/search", body) or {}
        return [self._person(p) for p in (data.get("people") or []) if isinstance(p, dict)]

    def enrich_person(self, *, full_name: Optional[str] = None, linkedin_url: Optional[str] = None,
                      company_name: Optional[str] = None, domain: Optional[str] = None) -> Optional[EnrichedPerson]:
        body: dict = {}
        if linkedin_url:
            body["linkedin_url"] = linkedin_url
        if full_name:
            parts = full_name.split()
            body["first_name"], body["last_name"] = parts[0], parts[-1]
        if domain:
            body["domain"] = domain
        if company_name:
            body["organization_name"] = company_name
        if not body:
            return None
        person = (self._post("/v1/people/match", body) or {}).get("person")
        return self._person(person) if isinstance(person, dict) else None

    def get_company_enrichment(self, *, company_name: str, domain: Optional[str] = None) -> Optional[CompanyEnrichment]:
        if not domain:
            return None
        if not self._key:
            raise EnrichmentNotConfigured("APOLLO_API_KEY is not configured.")
        org = (self._client.request("GET", "/v1/organizations/enrich",
                                    params={"domain": domain}) or {}).get("organization")
        if not isinstance(org, dict):
            return None
        return CompanyEnrichment(name=org.get("name"), domain=org.get("primary_domain"),
                                 linkedin_url=org.get("linkedin_url"), industry=org.get("industry"),
                                 country=org.get("country"), provider_company_id=org.get("id"),
                                 source=self.source_label)

    def health_check(self) -> tuple[HealthStatus, str]:
        if not self._key:
            return HealthStatus.NOT_CONFIGURED, "No Apollo API key configured."
        try:
            self._post("/v1/mixed_people/search", {"page": 1, "per_page": 1})
            return HealthStatus.HEALTHY, "Apollo reachable and authenticated."
        except EnrichmentAuthError:
            return HealthStatus.AUTHENTICATION_FAILED, "Apollo rejected the API key."
        except EnrichmentForbidden:
            return HealthStatus.RESTRICTED, "Apollo access forbidden."
        except EnrichmentRateLimited:
            return HealthStatus.RATE_LIMITED, "Apollo rate limit reached."
        except EnrichmentUnavailable:
            return HealthStatus.UNAVAILABLE, "Apollo request failed."
