"""ContactOut configuration (Prompt 44).

Verifies env-driven config, conservative credit defaults, and the config-level
status helper (never a live check; token never surfaced by the status property)."""

from __future__ import annotations

from config.settings import Settings


def test_defaults_are_conservative_and_not_configured():
    s = Settings(_env_file=None)
    assert s.contactout_api_token is None
    assert s.contactout_base_url == "https://api.contactout.com"
    assert s.contactout_config_status == "NOT_CONFIGURED"
    assert s.contactout_max_poc_searches_per_opportunity == 3
    assert s.contactout_max_enrichments_per_opportunity == 2
    assert s.contactout_people_search_rate_per_minute == 60
    assert s.contactout_other_rate_per_minute == 1000
    assert s.contactout_cache_ttl_hours == 168


def test_status_configured_with_token():
    s = Settings(_env_file=None, CONTACTOUT_API_TOKEN="tok")
    assert s.contactout_config_status == "CONFIGURED"


def test_status_disabled_wins_over_token():
    s = Settings(_env_file=None, CONTACTOUT_API_TOKEN="tok", CONTACTOUT_ENABLED=False)
    assert s.contactout_config_status == "DISABLED"


def test_base_url_configurable():
    s = Settings(_env_file=None, CONTACTOUT_BASE_URL="https://sandbox.contactout.test")
    assert s.contactout_base_url == "https://sandbox.contactout.test"
