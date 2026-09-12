"""Normalized enrichment-provider interface, capabilities, result models, exceptions.

Providers translate their own responses into these types so the waterfall/UI never
see provider-specific formats. Nothing is fabricated: a value a provider did not
return stays None; a provider's verification result is preserved verbatim.
"""

from __future__ import annotations

from abc import ABC
from dataclasses import dataclass, field
from typing import Optional

from collectors.base import HealthStatus


# --- exceptions (typed so the waterfall maps state without fabricating) ------ #
class EnrichmentError(RuntimeError):
    """Base for every enrichment-provider error."""


class EnrichmentNotConfigured(EnrichmentError):
    """No API key configured — no request is attempted."""


class EnrichmentAuthError(EnrichmentError):
    """401 — credentials missing/invalid. Never retried."""


class EnrichmentForbidden(EnrichmentError):
    """403 — access forbidden / insufficient plan. Never retried."""


class EnrichmentRateLimited(EnrichmentError):
    """429 — rate limited after client-side retries."""


class EnrichmentUnavailable(EnrichmentError):
    """5xx / network / timeout after retries."""


class EnrichmentBadResponse(EnrichmentError):
    """Malformed / unparseable response."""


# --- capabilities (§10) — declared true only when implemented + documented --- #
@dataclass(frozen=True)
class ProviderCapabilities:
    person_search: bool = False
    person_enrichment: bool = False
    company_enrichment: bool = False
    email_finder: bool = False
    email_verification: bool = False
    decision_maker_search: bool = False


# --- normalized results ------------------------------------------------------ #
@dataclass
class EmailResult:
    """An email with its own provenance + verification (§20/§21)."""

    email: Optional[str] = None
    verification_status: str = "UNVERIFIED"   # VALID/INVALID/ACCEPT_ALL/WEBMAIL/DISPOSABLE/UNKNOWN/UNVERIFIED
    is_work: bool = True
    source: str = ""
    source_url: Optional[str] = None


@dataclass
class PhoneResult:
    """A phone with type + provenance (§22)."""

    number: Optional[str] = None
    phone_type: str = "UNKNOWN"               # BUSINESS_DIRECT/BUSINESS_MOBILE/COMPANY_SWITCHBOARD/UNKNOWN
    verification_status: str = "UNVERIFIED"
    source: str = ""
    source_url: Optional[str] = None


@dataclass
class EnrichedPerson:
    """A person as returned by a provider — only real, returned values."""

    full_name: Optional[str] = None
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    job_title: Optional[str] = None
    seniority: Optional[str] = None
    company_name: Optional[str] = None
    company_domain: Optional[str] = None
    linkedin_url: Optional[str] = None        # verbatim only; never constructed
    location: Optional[str] = None
    is_current: Optional[bool] = None
    provider_person_id: Optional[str] = None
    provider_company_id: Optional[str] = None
    work_email: Optional[EmailResult] = None
    personal_email: Optional[str] = None
    phone: Optional[PhoneResult] = None
    source: str = ""
    source_label: str = ""
    source_url: Optional[str] = None


@dataclass
class CompanyEnrichment:
    name: Optional[str] = None
    domain: Optional[str] = None
    linkedin_url: Optional[str] = None
    industry: Optional[str] = None
    country: Optional[str] = None
    provider_company_id: Optional[str] = None
    source: str = ""


@dataclass
class ProviderResult:
    """One provider operation's outcome."""

    provider: str
    status: str = "SUCCESS"   # SUCCESS/PARTIAL/NO_DATA/RATE_LIMITED/UNAUTHORIZED/FORBIDDEN/NOT_CONFIGURED/SOURCE_UNAVAILABLE/ERROR
    people: list[EnrichedPerson] = field(default_factory=list)
    company: Optional[CompanyEnrichment] = None
    error: Optional[str] = None


class EnrichmentProvider(ABC):
    """Base enrichment provider. Subclasses override only supported operations and
    declare matching capabilities."""

    name: str = "base"
    source_label: str = "Provider"
    capabilities: ProviderCapabilities = ProviderCapabilities()

    def is_configured(self) -> bool:
        return False

    # Capability methods — default: not supported (return empty / raise cleanly).
    def search_people(self, *, company_name: str, titles: list[str],
                      domain: Optional[str] = None, location: Optional[str] = None) -> list[EnrichedPerson]:
        return []

    def find_decision_makers(self, *, company_name: str, domain: Optional[str] = None) -> list[EnrichedPerson]:
        return []

    def enrich_person(self, *, full_name: Optional[str] = None, linkedin_url: Optional[str] = None,
                      company_name: Optional[str] = None, domain: Optional[str] = None) -> Optional[EnrichedPerson]:
        return None

    def find_business_email(self, *, full_name: str, domain: str) -> Optional[EmailResult]:
        return None

    def verify_email(self, email: str) -> Optional[EmailResult]:
        return None

    def get_company_enrichment(self, *, company_name: str, domain: Optional[str] = None) -> Optional[CompanyEnrichment]:
        return None

    def health_check(self) -> tuple[HealthStatus, str]:
        return HealthStatus.NOT_CONFIGURED, f"{self.name} not configured."
