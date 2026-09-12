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
from integrations.public_intelligence.opencorporates import OpenCorporatesProvider
from integrations.public_intelligence.public_registry import PublicRegistryProvider
from integrations.public_intelligence.rss import RssProvider
from integrations.public_intelligence.wikidata import WikidataProvider

# name -> factory. Kept explicit so enabling/disabling is transparent.
_FACTORIES = {
    "official_company": lambda **kw: OfficialCompanyProvider(),
    "github": lambda **kw: GitHubProvider(**kw),
    "wikidata": lambda **kw: WikidataProvider(**kw),
    "opencorporates": lambda **kw: OpenCorporatesProvider(http=kw.get("http")),
    "public_registry": lambda **kw: PublicRegistryProvider(),
    "rss": lambda **kw: RssProvider(),
}
_HTTP_PROVIDERS = ("github", "wikidata", "opencorporates")

PROVIDER_NAMES = tuple(_FACTORIES.keys())


def _provider_enabled(name: str) -> bool:
    s = get_settings()
    # OpenCorporates has its own token-gated toggle (needs a configured API token).
    if name == "opencorporates":
        return s.opencorporates_config_status == "CONFIGURED"
    return s.public_intelligence_provider_enabled(name)


def enabled_provider_names() -> list[str]:
    return [n for n in PROVIDER_NAMES if _provider_enabled(n)]


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
        providers.append(factory(http=http) if name in _HTTP_PROVIDERS else factory())
    return providers
