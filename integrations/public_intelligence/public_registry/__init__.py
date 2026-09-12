"""Public company/government registry provider — extensible abstraction only.

No universal public Indian company API is assumed (§15). This provides the provider
interface so a specific, legally/publicly accessible registry can be plugged in later
(implement discover_company/discover_public_contacts on a subclass and register it).
It never scrapes restricted government systems and, with no concrete registry
configured, returns nothing — never fabricated company data.
"""

from __future__ import annotations

from typing import Optional

from integrations.public_intelligence.base import PublicIntelligenceProvider
from integrations.public_intelligence.models import CompanyContext, PublicCompanyFacts


class PublicRegistryProvider(PublicIntelligenceProvider):
    name = "public_registry"
    source_label = "Public Registry"
    source_type = "public_registry"

    def discover_company(self, ctx: CompanyContext) -> Optional[PublicCompanyFacts]:
        # No concrete public registry is configured in this project (abstraction only).
        return None


__all__ = ["PublicRegistryProvider"]
