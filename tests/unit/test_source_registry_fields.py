"""The extended SourceDefinition metadata loads correctly from config/sources.yaml."""

from __future__ import annotations

from collectors.source_registry import (
    AuthenticationType,
    SourceCapability,
    get_registry,
)


def test_adzuna_metadata():
    adzuna = get_registry().get("adzuna")
    assert adzuna.provider == "Adzuna"
    assert adzuna.authentication_type is AuthenticationType.API_KEY_PAIR
    assert adzuna.credential_env_vars == ["ADZUNA_APP_ID", "ADZUNA_APP_KEY"]
    assert SourceCapability.JOBS in adzuna.capabilities
    assert adzuna.supports_india is True
    assert adzuna.reliability_tier == "TIER_2"
    assert adzuna.documentation_url


def test_jooble_metadata():
    jooble = get_registry().get("jooble")
    assert jooble.provider == "Jooble"
    assert jooble.authentication_type is AuthenticationType.API_KEY
    assert jooble.credential_env_vars == ["JOOBLE_API_KEY"]
    assert jooble.supports_india is True
    assert jooble.reliability_tier == "TIER_2"
    # Commercial use undocumented → requires review (never silently production-ok).
    assert jooble.commercial_use_status.value == "REQUIRES_REVIEW"


def test_capabilities_are_typed_enums():
    for source in get_registry().all():
        for cap in source.capabilities:
            assert isinstance(cap, SourceCapability)
