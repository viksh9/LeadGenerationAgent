"""Hunter provider — email discovery + verification (Prompt 49, §7).

Current documented API (api.hunter.io/v2, api_key query param):
    GET /v2/domain-search   — public emails for a company domain
    GET /v2/email-finder     — email for a known name + domain (never generated)
    GET /v2/email-verifier   — deliverability status
    GET /v2/account          — cheap key check (no credit) for health

Hunter is used as the email-focused / verification layer. It NEVER generates an
email from a naming pattern — email-finder returns a real Hunter result or nothing.
Exact response fields per Hunter's live docs — REQUIRES_REVIEW.
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
    ProviderCapabilities,
)
from integrations.enrichment.http import EnrichmentHttpClient

# Hunter verifier statuses → our normalized set (preserved verbatim, never upgraded).
_VERIFY = {"valid": "VALID", "invalid": "INVALID", "accept_all": "ACCEPT_ALL",
           "webmail": "WEBMAIL", "disposable": "DISPOSABLE", "unknown": "UNKNOWN"}


class HunterProvider(EnrichmentProvider):
    name = "hunter"
    source_label = "Hunter"
    capabilities = ProviderCapabilities(person_search=True, email_finder=True,
                                        email_verification=True, company_enrichment=True)

    def __init__(self, *, http: httpx.Client | None = None, sleep=None) -> None:
        s = get_settings()
        self._key = s.hunter_api_key
        self._client = EnrichmentHttpClient(
            base_url=s.hunter_base_url, auth_header="X-Unused", auth_value="", provider="hunter",
            requests_per_minute=s.enrichment_rate_per_minute, timeout_seconds=s.enrichment_timeout_seconds,
            http=http, **({"sleep": sleep} if sleep else {}))

    def is_configured(self) -> bool:
        return bool(self._key)

    def _get(self, path: str, params: dict):
        if not self._key:
            raise EnrichmentNotConfigured("HUNTER_API_KEY is not configured.")
        return self._client.request("GET", path, params={**params, "api_key": self._key})

    def find_business_email(self, *, full_name: str, domain: str) -> Optional[EmailResult]:
        parts = (full_name or "").split()
        if not parts or not domain:
            return None
        params = {"domain": domain, "first_name": parts[0], "last_name": parts[-1]}
        data = (self._get("/v2/email-finder", params) or {}).get("data") or {}
        email = data.get("email")
        if not email:
            return None
        vs = ((data.get("verification") or {}).get("status")) or ""
        return EmailResult(email=email, verification_status=_VERIFY.get(vs.lower(), "UNVERIFIED"),
                           is_work=True, source=self.source_label,
                           source_url=f"https://hunter.io/email-finder")

    def verify_email(self, email: str) -> Optional[EmailResult]:
        if not email:
            return None
        data = (self._get("/v2/email-verifier", {"email": email}) or {}).get("data") or {}
        status = (data.get("status") or data.get("result") or "").lower()
        return EmailResult(email=email, verification_status=_VERIFY.get(status, "UNKNOWN"),
                           source=self.source_label, source_url="https://hunter.io/email-verifier")

    def search_people(self, *, company_name: str, titles: list[str],
                      domain: Optional[str] = None, location: Optional[str] = None) -> list[EnrichedPerson]:
        if not domain:
            return []   # domain-search needs a domain; never guessed from name
        data = (self._get("/v2/domain-search", {"domain": domain, "limit": 10}) or {}).get("data") or {}
        people: list[EnrichedPerson] = []
        for e in (data.get("emails") or []):
            name = " ".join(p for p in (e.get("first_name"), e.get("last_name")) if p) or None
            people.append(EnrichedPerson(
                full_name=name, first_name=e.get("first_name"), last_name=e.get("last_name"),
                job_title=e.get("position"), company_name=company_name, company_domain=domain,
                linkedin_url=e.get("linkedin"),
                work_email=EmailResult(email=e.get("value"),
                                       verification_status=_VERIFY.get((e.get("verification") or {}).get("status", ""), "UNVERIFIED")
                                       if isinstance(e.get("verification"), dict) else "UNVERIFIED",
                                       source=self.source_label,
                                       source_url=f"https://hunter.io/companies/{domain}") if e.get("value") else None,
                source=self.name, source_label=self.source_label,
                source_url=f"https://hunter.io/companies/{domain}"))
        return people

    def health_check(self) -> tuple[HealthStatus, str]:
        if not self._key:
            return HealthStatus.NOT_CONFIGURED, "No Hunter API key configured."
        try:
            self._get("/v2/account", {})   # cheap key check, no enrichment credit
            return HealthStatus.HEALTHY, "Hunter reachable and authenticated."
        except EnrichmentAuthError:
            return HealthStatus.AUTHENTICATION_FAILED, "Hunter rejected the API key."
        except EnrichmentForbidden:
            return HealthStatus.RESTRICTED, "Hunter access forbidden."
        except EnrichmentRateLimited:
            return HealthStatus.RATE_LIMITED, "Hunter rate limit reached."
        except EnrichmentUnavailable:
            return HealthStatus.UNAVAILABLE, "Hunter request failed."
