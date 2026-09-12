"""Prospeo provider — person email/mobile enrichment + company (§8).

Current documented API (api.prospeo.io, header `X-KEY`):
    POST /email-finder    — work email for a known name + company (never generated)
    POST /mobile-finder    — mobile for a LinkedIn/profile identifier
Search/company endpoints vary by plan. Exact request/response per Prospeo's live docs —
REQUIRES_REVIEW. Enrichment runs only after a candidate is selected (credit-aware).
"""

from __future__ import annotations

from typing import Optional

import httpx

from collectors.base import HealthStatus
from config import get_settings
from integrations.enrichment.base import (
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

_VERIFY = {"valid": "VALID", "invalid": "INVALID", "accept_all": "ACCEPT_ALL",
           "catch_all": "ACCEPT_ALL", "unknown": "UNKNOWN", "risky": "UNKNOWN"}


class ProspeoProvider(EnrichmentProvider):
    name = "prospeo"
    source_label = "Prospeo"
    capabilities = ProviderCapabilities(person_enrichment=True, email_finder=True)

    def __init__(self, *, http: httpx.Client | None = None, sleep=None) -> None:
        s = get_settings()
        self._key = s.prospeo_api_key
        self._client = EnrichmentHttpClient(
            base_url=s.prospeo_base_url, auth_header="X-KEY", auth_value=self._key or "",
            provider="prospeo", requests_per_minute=s.enrichment_rate_per_minute,
            timeout_seconds=s.enrichment_timeout_seconds, http=http, **({"sleep": sleep} if sleep else {}))

    def is_configured(self) -> bool:
        return bool(self._key)

    def _post(self, path: str, body: dict):
        if not self._key:
            raise EnrichmentNotConfigured("PROSPEO_API_KEY is not configured.")
        return self._client.request("POST", path, json=body)

    def find_business_email(self, *, full_name: str, domain: str) -> Optional[EmailResult]:
        parts = (full_name or "").split()
        if not parts or not domain:
            return None
        raw = self._post("/email-finder", {"company": domain, "first_name": parts[0],
                                           "last_name": parts[-1]}) or {}
        resp = raw.get("response") if isinstance(raw.get("response"), dict) else raw
        email = resp.get("email") if isinstance(resp, dict) else None
        if not email:
            return None
        status = (resp.get("email_status") or resp.get("status") or "").lower()
        return EmailResult(email=email, verification_status=_VERIFY.get(status, "UNVERIFIED"),
                           source=self.source_label, source_url="https://prospeo.io")

    def enrich_person(self, *, full_name: Optional[str] = None, linkedin_url: Optional[str] = None,
                      company_name: Optional[str] = None, domain: Optional[str] = None) -> Optional[EnrichedPerson]:
        email_result = None
        if full_name and domain:
            email_result = self.find_business_email(full_name=full_name, domain=domain)
        phone_result = None
        if linkedin_url:
            raw = self._post("/mobile-finder", {"url": linkedin_url}) or {}
            resp = raw.get("response") if isinstance(raw.get("response"), dict) else raw
            num = resp.get("mobile") or resp.get("raw_format") if isinstance(resp, dict) else None
            if num:
                phone_result = PhoneResult(number=num, phone_type="BUSINESS_MOBILE", source=self.source_label)
        if not email_result and not phone_result:
            return None
        return EnrichedPerson(full_name=full_name, company_name=company_name, company_domain=domain,
                              linkedin_url=linkedin_url, work_email=email_result, phone=phone_result,
                              source=self.name, source_label=self.source_label)

    def health_check(self) -> tuple[HealthStatus, str]:
        if not self._key:
            return HealthStatus.NOT_CONFIGURED, "No Prospeo API key configured."
        try:
            # A minimal authenticated call (no bulk enrichment); maps auth/rate errors.
            self._post("/account-information", {})
            return HealthStatus.HEALTHY, "Prospeo reachable and authenticated."
        except EnrichmentAuthError:
            return HealthStatus.AUTHENTICATION_FAILED, "Prospeo rejected the API key."
        except EnrichmentForbidden:
            return HealthStatus.RESTRICTED, "Prospeo access forbidden."
        except EnrichmentRateLimited:
            return HealthStatus.RATE_LIMITED, "Prospeo rate limit reached."
        except EnrichmentUnavailable:
            return HealthStatus.UNAVAILABLE, "Prospeo request failed."
