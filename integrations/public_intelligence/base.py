"""Common provider interface for free/public intelligence.

Providers are decoupled from the POC service and from each other. Each returns
NORMALIZED records (models.py) — never provider-specific formats. A provider that
cannot answer a given query returns empties, never fabricated data (§29).
"""

from __future__ import annotations

from abc import ABC
from typing import Optional

from collectors.base import HealthStatus
from integrations.public_intelligence.models import (
    CompanyContext,
    ProviderResult,
    PublicCompanyFacts,
    PublicContact,
    PublicPerson,
)


class PublicIntelligenceProvider(ABC):
    """Base provider. Subclasses override only the capabilities they support."""

    name: str = "base"
    source_label: str = "Public source"
    source_type: str = "public_source"

    def discover_company(self, ctx: CompanyContext) -> Optional[PublicCompanyFacts]:
        """Public company identity facts (website/country/industry/ids). Default: none."""
        return None

    def discover_people(self, ctx: CompanyContext, roles: list[str]) -> list[PublicPerson]:
        """Real people matching the recommended roles. Default: none."""
        return []

    def discover_public_contacts(self, ctx: CompanyContext) -> list[PublicContact]:
        """Explicitly-published company contacts (emails/phones). Default: none."""
        return []

    def health_check(self) -> tuple[HealthStatus, str]:
        """Cheap connectivity/config check. Default: healthy (offline providers)."""
        return HealthStatus.HEALTHY, f"{self.name} ready."

    def discover(self, ctx: CompanyContext, roles: list[str]) -> ProviderResult:
        """Run all supported capabilities and package a normalized ProviderResult.
        Any provider error is surfaced on the result — never raised as fabricated data."""
        result = ProviderResult(provider=self.name)
        try:
            result.company_facts = self.discover_company(ctx)
            result.people = self.discover_people(ctx, roles)
            result.contacts = self.discover_public_contacts(ctx)
            result.records_found = len(result.people) + len(result.contacts) + (1 if result.company_facts else 0)
            result.status = "OK" if result.records_found else "EMPTY"
        except ProviderUnavailable as exc:
            result.status, result.error = "UNAVAILABLE", str(exc)
        except ProviderRateLimited as exc:
            result.status, result.error = "RATE_LIMITED", str(exc)
        except Exception as exc:  # noqa: BLE001 - never let a provider fabricate/raise up
            result.status, result.error = "ERROR", type(exc).__name__
        return result


class ProviderUnavailable(RuntimeError):
    """Source unreachable / 5xx / timeout after retries."""


class ProviderRateLimited(RuntimeError):
    """Source rate limited (429 / documented limit)."""
