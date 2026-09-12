"""Free-first provider registry (§30).

Builds the set of ENABLED public-intelligence providers from configuration. Each
provider can be toggled independently; providers with no concrete source
(public_registry) or no configuration (rss without feeds) default off.
"""

from __future__ import annotations

from typing import Optional

import httpx

from config import get_settings
from integrations.public_intelligence.base import PublicIntelligenceProvider
from integrations.public_intelligence.github import GitHubProvider
from integrations.public_intelligence.official_company import OfficialCompanyProvider
from integrations.public_intelligence.public_registry import PublicRegistryProvider
from integrations.public_intelligence.rss import RssProvider
from integrations.public_intelligence.wikidata import WikidataProvider

# name -> factory. Kept explicit so enabling/disabling is transparent.
_FACTORIES = {
    "official_company": lambda **kw: OfficialCompanyProvider(),
    "github": lambda **kw: GitHubProvider(**kw),
    "wikidata": lambda **kw: WikidataProvider(**kw),
    "public_registry": lambda **kw: PublicRegistryProvider(),
    "rss": lambda **kw: RssProvider(),
}

PROVIDER_NAMES = tuple(_FACTORIES.keys())


def enabled_provider_names() -> list[str]:
    s = get_settings()
    return [n for n in PROVIDER_NAMES if s.public_intelligence_provider_enabled(n)]


def build_providers(*, names: Optional[list[str]] = None,
                    http: httpx.Client | None = None) -> list[PublicIntelligenceProvider]:
    """Instantiate the enabled providers (optionally restricted to `names`).
    `http` is injectable so tests can stub network providers."""
    wanted = names if names is not None else enabled_provider_names()
    providers: list[PublicIntelligenceProvider] = []
    for name in wanted:
        factory = _FACTORIES.get(name)
        if factory is None:
            continue
        # Only the network providers accept an injected http client.
        if name in ("github", "wikidata"):
            providers.append(factory(http=http))
        else:
            providers.append(factory())
    return providers
