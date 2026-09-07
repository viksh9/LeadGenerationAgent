"""Offline tests for the Jooble collector (no real network — httpx.MockTransport).

Covers mapping (provider fields → RawRecordDraft), pagination, IT relevance
filtering, provenance, and health-check classification (auth / rate-limit /
unavailable). No live credentials are used.
"""

from __future__ import annotations

import json

import httpx
import pytest

from collectors.base import FetchRequest, HealthStatus
from collectors.errors import SourceAuthError, SourceRateLimitError
from collectors.jobs.jooble import (
    JoobleClient,
    JoobleConfig,
    JoobleJobCollector,
    map_job,
)
from collectors.source_registry import get_registry

SAMPLE = {
    "totalCount": 42,
    "jobs": [
        {
            "id": 111, "title": "Senior Python Developer", "location": "Bengaluru",
            "snippet": "Build <b>backend</b> APIs in Python &amp; AWS.",
            "salary": "₹20,00,000 - ₹30,00,000", "source": "naukri", "type": "Full-time",
            "link": "https://in.jooble.org/desc/111", "company": "Acme Tech",
            "updated": "2026-09-01T10:00:00Z",
        },
        {
            "id": 222, "title": "Warehouse Packer", "location": "Pune",
            "snippet": "Warehouse packing and delivery loading.", "salary": "",
            "source": "x", "type": "", "link": "https://in.jooble.org/desc/222",
            "company": "LogiCo", "updated": "2026-09-02T10:00:00Z",
        },
    ],
}


def _collector(handler, *, config=None):
    cfg = config or JoobleConfig(api_key="TESTKEY", host="in.jooble.org", location="India")
    client = JoobleClient(cfg, http=httpx.Client(transport=httpx.MockTransport(handler)))
    source = get_registry().get("jooble")
    return JoobleJobCollector(source, config=cfg, client=client)


def test_map_job_maps_provider_fields():
    draft = map_job(SAMPLE["jobs"][0], host="in.jooble.org", query="python", location="India")
    assert draft.source_id == "jooble"
    assert draft.external_id == "111"                       # provider id -> external_id
    assert draft.source_url == "https://in.jooble.org/desc/111"
    assert draft.title == "Senior Python Developer"
    assert draft.description == "Build backend APIs in Python & AWS."   # HTML stripped/unescaped
    assert draft.company_name == "Acme Tech"
    assert draft.location == "Bengaluru"
    assert draft.contract_type == "Full-time"
    assert draft.published_at is not None
    assert draft.is_synthetic is False                      # real provenance
    assert draft.raw_payload["_collection"]["collector"] == "jooble"


def test_missing_fields_stay_null_not_faked():
    draft = map_job({"id": 5, "title": "Dev", "link": "https://x/5"},
                    host="jooble.org", query="dev", location="India")
    assert draft.company_name is None
    assert draft.salary is None
    assert draft.location is None
    assert draft.published_at is None


def test_fetch_builds_post_body_and_maps(monkeypatch):
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "POST"
        assert request.url.path.endswith("/api/TESTKEY")     # key in URL path
        seen.update(json.loads(request.content))
        return httpx.Response(200, json=SAMPLE)

    collector = _collector(handler)
    result = collector.fetch(FetchRequest(query="python developer", location="India", page=1))
    assert seen["keywords"] == "python developer"
    assert seen["location"] == "India"
    # The nurse posting is filtered as clearly non-IT; the Python role is kept.
    assert result.records_count == 1
    assert result.records[0].external_id == "111"
    assert result.total_records == 42
    assert result.has_more is True                           # 1*20 < 42
    assert any("non-IT" in w for w in result.warnings)


def test_not_configured_raises_and_health_reports():
    cfg = JoobleConfig(api_key=None)
    source = get_registry().get("jooble")
    collector = JoobleJobCollector(source, config=cfg,
                                   client=JoobleClient(cfg, http=httpx.Client()))
    health = collector.health_check()
    assert health.status is HealthStatus.NOT_CONFIGURED


def test_health_check_healthy_on_200():
    collector = _collector(lambda req: httpx.Response(200, json={"totalCount": 0, "jobs": []}))
    assert collector.health_check().status is HealthStatus.HEALTHY


def test_health_check_auth_failed_on_403():
    collector = _collector(lambda req: httpx.Response(403, text="Access Denied"))
    assert collector.health_check().status is HealthStatus.AUTHENTICATION_FAILED


def test_health_check_rate_limited_on_429():
    collector = _collector(lambda req: httpx.Response(429, text="Too Many Requests"))
    assert collector.health_check().status is HealthStatus.RATE_LIMITED


def test_health_check_unavailable_on_500():
    collector = _collector(lambda req: httpx.Response(500, text="err"))
    assert collector.health_check().status is HealthStatus.UNAVAILABLE


def test_client_raises_typed_errors():
    cfg = JoobleConfig(api_key="K", host="jooble.org")
    auth_client = JoobleClient(cfg, http=httpx.Client(transport=httpx.MockTransport(
        lambda req: httpx.Response(403))))
    with pytest.raises(SourceAuthError):
        auth_client.search({"keywords": "x", "location": "India", "page": 1})

    rate_client = JoobleClient(cfg, http=httpx.Client(transport=httpx.MockTransport(
        lambda req: httpx.Response(429))), sleep=lambda _s: None)
    with pytest.raises(SourceRateLimitError):
        rate_client.search({"keywords": "x", "location": "India", "page": 1})
