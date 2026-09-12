"""Free/public company + POC intelligence layer.

Provider-based (official company website, GitHub, Wikidata, + public-registry/RSS
abstractions). Discovers legitimately PUBLIC company and POC information without paid
providers. Real data only: no guessed emails, no fabricated people, no fake API
responses. See docs/PUBLIC_INTELLIGENCE.md.
"""

from integrations.public_intelligence.base import (
    ProviderRateLimited,
    ProviderUnavailable,
    PublicIntelligenceProvider,
)
from integrations.public_intelligence.models import (
    CompanyContext,
    ProviderResult,
    PublicCompanyFacts,
    PublicContact,
    PublicPerson,
)
from integrations.public_intelligence.registry import (
    PROVIDER_NAMES,
    build_providers,
    enabled_provider_names,
)

__all__ = [
    "PublicIntelligenceProvider",
    "ProviderUnavailable",
    "ProviderRateLimited",
    "CompanyContext",
    "ProviderResult",
    "PublicPerson",
    "PublicContact",
    "PublicCompanyFacts",
    "build_providers",
    "enabled_provider_names",
    "PROVIDER_NAMES",
]
