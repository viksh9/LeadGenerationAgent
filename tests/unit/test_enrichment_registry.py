"""Enrichment provider registry + capabilities (Prompt 49, §10).

Verifies capability declarations match documented provider contracts, config gating
(no key ⇒ not configured, no build side effects), and the priority ordering.
"""

from __future__ import annotations

from config import get_settings
from integrations.enrichment.registry import (
    CAPABILITIES,
    PROVIDER_PRIORITY,
    build_provider,
    configured_provider_names,
    provider_configured,
)


def test_priority_order_public_then_paid():
    assert PROVIDER_PRIORITY == ("contactout", "apollo", "lusha", "prospeo", "hunter")


def test_declared_capabilities():
    assert CAPABILITIES["apollo"].person_search is True
    assert CAPABILITIES["lusha"].person_enrichment is True
    assert CAPABILITIES["hunter"].email_verification is True
    assert CAPABILITIES["prospeo"].email_finder is True
    # Providers that do not offer people-search must not claim it.
    assert CAPABILITIES["lusha"].person_search is False
    assert CAPABILITIES["prospeo"].person_search is False


def test_provider_configured_gated_by_key():
    s = get_settings()
    prev = s.apollo_api_key
    s.apollo_api_key = None
    try:
        assert provider_configured("apollo") is False
        assert "apollo" not in configured_provider_names()
        s.apollo_api_key = "k"
        assert provider_configured("apollo") is True
        assert "apollo" in configured_provider_names()
    finally:
        s.apollo_api_key = prev


def test_build_unknown_returns_none():
    assert build_provider("does-not-exist") is None


def test_build_known_returns_provider_instance():
    inst = build_provider("hunter")
    assert inst is not None and inst.name == "hunter"
