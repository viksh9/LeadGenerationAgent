"""Source connectivity + collector-registry tests (offline).

Verifies the registry dispatch, the connectivity service's truthful status
classification (CONNECTED only after a real success; AUTHENTICATION_FAILED /
RATE_LIMITED / TEMPORARILY_UNAVAILABLE otherwise), persistence to source_health,
and the /sources status/check API. No live credentials or real network.
"""

from __future__ import annotations

import httpx
import pytest

from collectors.connectivity import check_source_connection, get_source_health
from collectors.jobs.jooble import JoobleClient, JoobleConfig, JoobleJobCollector
from collectors.registry import (
    CollectorNotImplemented,
    build_collector,
    is_runnable,
    runnable_source_ids,
)
from collectors.source_registry import get_registry
from database.models import SourceConnectionStatus


# --------------------------------------------------------------------------- #
# Registry
# --------------------------------------------------------------------------- #
def test_registry_lists_runnable_sources():
    assert runnable_source_ids() == frozenset({"adzuna", "jooble"})
    assert is_runnable("adzuna") and is_runnable("jooble")
    assert not is_runnable("government_open_data")


def test_build_collector_unknown_raises():
    with pytest.raises(CollectorNotImplemented):
        build_collector("not_a_source")


def test_build_collector_returns_collector():
    from collectors.jobs.adzuna import AdzunaJobCollector

    assert isinstance(build_collector("adzuna"), AdzunaJobCollector)
    assert isinstance(build_collector("jooble"), JoobleJobCollector)


# --------------------------------------------------------------------------- #
# Connectivity service — classification + persistence (offline)
# --------------------------------------------------------------------------- #
def _jooble_collector(status_code, *, json=None):
    cfg = JoobleConfig(api_key="TESTKEY", host="in.jooble.org")
    handler = lambda req: httpx.Response(status_code, json=json or {"totalCount": 0, "jobs": []})
    client = JoobleClient(cfg, http=httpx.Client(transport=httpx.MockTransport(handler)),
                          sleep=lambda _s: None)
    return JoobleJobCollector(get_registry().get("jooble"), config=cfg, client=client)


@pytest.mark.parametrize("code,expected", [
    (200, SourceConnectionStatus.CONNECTED),
    (403, SourceConnectionStatus.AUTHENTICATION_FAILED),
    (429, SourceConnectionStatus.RATE_LIMITED),
    (500, SourceConnectionStatus.TEMPORARILY_UNAVAILABLE),
])
def test_connectivity_classifies_and_persists(seed_session, monkeypatch, code, expected):
    # Force build_collector to return our mocked-HTTP collector (no real network).
    monkeypatch.setattr("collectors.connectivity.build_collector",
                        lambda source_id: _jooble_collector(code))
    result = check_source_connection(seed_session, "jooble")
    assert result.status is expected
    assert result.performed_request is True
    health = get_source_health(seed_session, "jooble")
    assert health.connection_status is expected
    assert health.last_checked_at is not None
    if expected is SourceConnectionStatus.CONNECTED:
        assert health.last_success_at is not None and health.checks_ok == 1
        assert health.last_error is None
    else:
        assert health.last_failure_at is not None
        assert health.last_error


def test_connectivity_not_configured_makes_no_request(seed_session, monkeypatch):
    for var in ("JOOBLE_API_KEY",):
        monkeypatch.delenv(var, raising=False)
    # A collector with no key must not perform a request.
    cfg = JoobleConfig(api_key=None)
    monkeypatch.setattr(
        "collectors.connectivity.build_collector",
        lambda source_id: JoobleJobCollector(get_registry().get("jooble"), config=cfg,
                                             client=JoobleClient(cfg, http=httpx.Client())),
    )
    result = check_source_connection(seed_session, "jooble")
    assert result.status is SourceConnectionStatus.NOT_CONFIGURED
    assert result.performed_request is False


def test_connectivity_non_runnable_source_no_network(seed_session):
    result = check_source_connection(seed_session, "government_open_data")
    assert result.status is SourceConnectionStatus.NOT_CONFIGURED
    assert result.performed_request is False


# --------------------------------------------------------------------------- #
# API
# --------------------------------------------------------------------------- #
def test_sources_api_reports_real_only_mode_and_capabilities(client):
    body = client.get("/sources").json()
    assert body["data_mode"] == "REAL_ONLY"
    assert body["any_connected"] is False
    jooble = next(i for i in body["items"] if i["source_id"] == "jooble")
    assert jooble["capabilities"]
    assert jooble["supports_india"] is True
    assert jooble["reliability_tier"] == "TIER_2"
    assert jooble["connection_status"] is None          # never checked yet


def test_sources_status_alias(client):
    assert client.get("/sources/status").status_code == 200


def test_check_endpoint_not_configured_no_network(client):
    body = client.post("/sources/adzuna/check").json()
    assert body["connection_status"] == "NOT_CONFIGURED"
    assert body["performed_request"] is False
