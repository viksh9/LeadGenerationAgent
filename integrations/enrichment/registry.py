"""Enrichment provider registry + capabilities (Prompt 49, §10).

Declares each paid provider and its capabilities, and builds instances gated by
configuration. Capabilities are declared true only where implemented + supported by
the provider's documented contract.
"""

from __future__ import annotations

from typing import Optional

import httpx

from config import get_settings
from integrations.enrichment.base import EnrichmentProvider, ProviderCapabilities
from integrations.enrichment.providers.apollo import ApolloProvider
from integrations.enrichment.providers.hunter import HunterProvider
from integrations.enrichment.providers.lusha import LushaProvider
from integrations.enrichment.providers.prospeo import ProspeoProvider

_FACTORIES = {
    "apollo": ApolloProvider,
    "lusha": LushaProvider,
    "hunter": HunterProvider,
    "prospeo": ProspeoProvider,
}

# Paid enrichment providers. ContactOut is a first-class provider too but has its own
# integration package + endpoints (integrations/contactout); it is surfaced in admin
# status separately. Priority order (§12) — official/public first, then:
PROVIDER_PRIORITY = ("contactout", "apollo", "lusha", "prospeo", "hunter")
PROVIDER_NAMES = tuple(_FACTORIES.keys())

CAPABILITIES: dict[str, ProviderCapabilities] = {
    "apollo": ApolloProvider.capabilities,
    "lusha": LushaProvider.capabilities,
    "hunter": HunterProvider.capabilities,
    "prospeo": ProspeoProvider.capabilities,
}


def provider_configured(name: str) -> bool:
    return get_settings().enrichment_provider_status(name) == "CONFIGURED"


def build_provider(name: str, *, http: httpx.Client | None = None) -> Optional[EnrichmentProvider]:
    factory = _FACTORIES.get(name)
    if factory is None:
        return None
    return factory(http=http)


def configured_provider_names() -> list[str]:
    return [n for n in _FACTORIES if provider_configured(n)]
