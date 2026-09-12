"""Offline tests for the Greenhouse + Lever ATS collectors (httpx.MockTransport).

Covers mapping, IT-relevance filtering, provenance, board/site validation, and
health-check classification. No real network, no credentials.
"""

from __future__ import annotations

import httpx
import pytest

from collectors.base import FetchRequest, HealthStatus
from collectors.errors import CollectorError, SourceAuthError, SourceRateLimitError
from collectors.ats import greenhouse as gh
from collectors.ats import lever as lv
from collectors.source_registry import SourceCategory, SourceDefinition, SourceType


def _src(sid):
    return SourceDefinition(source_id=sid, name=sid, category=SourceCategory.COMPANY,
                            source_type=SourceType.PUBLIC_WEB)


# --------------------------------------------------------------------------- #
# Greenhouse
# --------------------------------------------------------------------------- #
GH_PAYLOAD = {
    "meta": {"total": 2},
    "jobs": [
        {"id": 123, "title": "Senior Backend Engineer (Python)", "updated_at": "2026-09-01T10:00:00Z",
         "location": {"name": "Bengaluru, India"}, "absolute_url": "https://boards.greenhouse.io/acme/jobs/123",
         "company_name": "Acme", "content": "Build &lt;b&gt;APIs&lt;/b&gt; in Python and AWS."},
        {"id": 124, "title": "Office Receptionist", "updated_at": "2026-09-02T10:00:00Z",
         "location": {"name": "Pune, India"}, "absolute_url": "https://boards.greenhouse.io/acme/jobs/124",
         "company_name": "Acme", "content": "Front desk duties."},
    ],
}


def _gh_collector(handler, boards=("acme",)):
    cfg = gh.GreenhouseConfig(boards=list(boards))
    client = gh.GreenhouseClient(cfg, http=httpx.Client(transport=httpx.MockTransport(handler)))
    return gh.GreenhouseCollector(_src("greenhouse"), config=cfg, client=client)


def test_greenhouse_maps_and_filters():
    col = _gh_collector(lambda r: httpx.Response(200, json=GH_PAYLOAD))
    res = col.fetch(FetchRequest(board="acme"))
    assert res.total_records == 2
    assert res.records_count == 1                      # receptionist filtered as non-IT
    d = res.records[0]
    assert d.source_id == "greenhouse" and d.is_synthetic is False
    assert d.external_id == "123"
    assert d.source_url == "https://boards.greenhouse.io/acme/jobs/123"
    assert d.location == "Bengaluru, India"
    assert d.description == "Build APIs in Python and AWS."
    assert d.raw_payload["_collection"]["board"] == "acme"


def test_greenhouse_invalid_board_rejected():
    col = _gh_collector(lambda r: httpx.Response(200, json=GH_PAYLOAD))
    with pytest.raises(CollectorError):
        col._client.list_jobs("bad token!")           # space + '!' invalid


def test_greenhouse_health_statuses():
    assert _gh_collector(lambda r: httpx.Response(200, json={"jobs": [], "meta": {}})).health_check().status is HealthStatus.HEALTHY
    assert _gh_collector(lambda r: httpx.Response(403)).health_check().status is HealthStatus.AUTHENTICATION_FAILED
    # No board configured -> NOT_CONFIGURED (DISCOVERY_REQUIRED at the source level).
    col = gh.GreenhouseCollector(_src("greenhouse"), config=gh.GreenhouseConfig(boards=[]),
                                 client=gh.GreenhouseClient(gh.GreenhouseConfig(), http=httpx.Client()))
    assert col.health_check().status is HealthStatus.NOT_CONFIGURED


# --------------------------------------------------------------------------- #
# Lever
# --------------------------------------------------------------------------- #
LV_PAYLOAD = [
    {"id": "abc-1", "text": "Full Stack Engineer", "categories": {"location": "Hyderabad, India",
     "commitment": "Full-time", "team": "Engineering"}, "hostedUrl": "https://jobs.lever.co/acme/abc-1",
     "createdAt": 1567026000000, "descriptionPlain": "React and Node.js role."},
    {"id": "abc-2", "text": "Delivery Driver", "categories": {"location": "Pune, India"},
     "hostedUrl": "https://jobs.lever.co/acme/abc-2", "createdAt": 1567026000000,
     "descriptionPlain": "Warehouse delivery."},
]


def _lv_collector(handler, sites=("acme",)):
    cfg = lv.LeverConfig(sites=list(sites))
    client = lv.LeverClient(cfg, http=httpx.Client(transport=httpx.MockTransport(handler)))
    return lv.LeverCollector(_src("lever"), config=cfg, client=client)


def test_lever_maps_and_filters():
    col = _lv_collector(lambda r: httpx.Response(200, json=LV_PAYLOAD))
    res = col.fetch(FetchRequest(board="acme", limit=10))
    assert res.total_records == 2
    assert res.records_count == 1                      # driver filtered as non-IT
    d = res.records[0]
    assert d.source_id == "lever" and d.is_synthetic is False
    assert d.external_id == "abc-1"
    assert d.source_url == "https://jobs.lever.co/acme/abc-1"
    assert d.location == "Hyderabad, India"
    assert d.contract_type == "Full-time"
    assert d.published_at is not None                  # epoch-ms parsed
    assert d.company_name == "acme"


def test_lever_health_statuses():
    assert _lv_collector(lambda r: httpx.Response(200, json=[])).health_check().status is HealthStatus.HEALTHY
    assert _lv_collector(lambda r: httpx.Response(429), ).health_check().status is HealthStatus.RATE_LIMITED
    col = lv.LeverCollector(_src("lever"), config=lv.LeverConfig(sites=[]),
                            client=lv.LeverClient(lv.LeverConfig(), http=httpx.Client()))
    assert col.health_check().status is HealthStatus.NOT_CONFIGURED


def test_lever_client_typed_errors():
    cfg = lv.LeverConfig(sites=["acme"])
    auth = lv.LeverClient(cfg, http=httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(403))))
    with pytest.raises(SourceAuthError):
        auth.list_postings("acme", limit=1)
    rate = lv.LeverClient(cfg, http=httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(429))),
                          sleep=lambda _s: None)
    with pytest.raises(SourceRateLimitError):
        rate.list_postings("acme", limit=1)


# --------------------------------------------------------------------------- #
# India-only ATS filter (Prompt: India-first ATS targeting)
# --------------------------------------------------------------------------- #
_GH_MIXED = {
    "meta": {"total": 2},
    "jobs": [
        {"id": 1, "title": "Senior Backend Engineer (Python)", "updated_at": "2026-09-01T10:00:00Z",
         "location": {"name": "Bengaluru, Karnataka, India"},
         "absolute_url": "https://boards.greenhouse.io/acme/jobs/1", "company_name": "Acme",
         "content": "Python + AWS."},
        {"id": 2, "title": "Senior Backend Engineer (Python)", "updated_at": "2026-09-01T10:00:00Z",
         "location": {"name": "San Francisco, California, United States"},
         "absolute_url": "https://boards.greenhouse.io/acme/jobs/2", "company_name": "Acme",
         "content": "Python + AWS."},
    ],
}


def _gh_mixed_collector(india_only: bool):
    cfg = gh.GreenhouseConfig(boards=["acme"], india_only=india_only)
    client = gh.GreenhouseClient(cfg, http=httpx.Client(
        transport=httpx.MockTransport(lambda r: httpx.Response(200, json=_GH_MIXED))))
    return gh.GreenhouseCollector(_src("greenhouse"), config=cfg, client=client)


def test_greenhouse_india_only_keeps_only_india_roles():
    res = _gh_mixed_collector(india_only=True).fetch(FetchRequest(board="acme"))
    assert res.records_count == 1
    assert "India" in res.records[0].location
    assert any("non-India" in w for w in res.warnings)


def test_greenhouse_india_only_disabled_keeps_all():
    res = _gh_mixed_collector(india_only=False).fetch(FetchRequest(board="acme"))
    assert res.records_count == 2


def test_is_india_location_helper():
    from config.locations_in import is_india_location
    assert is_india_location("Bengaluru, Karnataka, India")
    assert is_india_location("Gurgaon")               # alias
    assert is_india_location("Hyderabad")
    assert not is_india_location("San Francisco, California, United States")
    assert not is_india_location("London, UK")
    assert not is_india_location("")
