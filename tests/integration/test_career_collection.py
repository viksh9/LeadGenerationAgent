"""Integration: CareerPageCollector -> JobCollectionService persistence.

Offline (httpx.MockTransport + injected robots). Verifies career-page records
persist as RawSourceRecords and dedup on a second run.
"""

from __future__ import annotations

import httpx

from collectors.base import FetchRequest
from collectors.company.career_page import CareerPageCollector
from collectors.company.config import CareerCollectorConfig
from collectors.company.robots import RobotsPolicy
from collectors.company.sources import CareerSourceDefinition, RobotsStatus, TermsStatus
from collectors.service import JobCollectionService
from database.raw_repository import list_raw_records
from tests.fixtures import career_pages as fx

BASE = "https://careers.example.com/careers"


def _handler(r):
    if r.url.path.endswith("/robots.txt"):
        return httpx.Response(200, headers={"content-type": "text/plain"}, text="User-agent: *\nAllow: /")
    return httpx.Response(200, headers={"content-type": "text/html"}, text=fx.JSONLD_SINGLE)


def _collector():
    source = CareerSourceDefinition(
        source_id="example_co", company_name="Example Co", company_domain="example.com",
        career_url=BASE, enabled=True, terms_status=TermsStatus.ALLOWED, robots_status=RobotsStatus.ALLOWED,
    )
    http = httpx.Client(transport=httpx.MockTransport(_handler), follow_redirects=False)
    robots = RobotsPolicy(lambda url: "User-agent: *\nAllow: /", user_agent="test")
    return CareerPageCollector(
        source, config=CareerCollectorConfig(requests_per_minute=0, max_pages=1),
        http=http, robots=robots, sleep=lambda *_: None,
    )


def test_career_records_persist(seed_session):
    summary = JobCollectionService(seed_session).collect(_collector(), [FetchRequest()])
    assert summary.accepted == 1
    stored = list_raw_records(seed_session, source_id="example_co")
    assert len(stored) == 1
    rec = stored[0]
    assert rec.company_name == "Globex Tech"
    assert rec.company_domain == "globex.example"
    assert "Java" in rec.technologies
    assert rec.is_synthetic is False
    assert rec.last_seen_at is not None
    assert rec.raw_payload["it_relevance"] == "RELEVANT"


def test_career_second_run_dedups(seed_session):
    service = JobCollectionService(seed_session)
    first = service.collect(_collector(), [FetchRequest()])
    second = service.collect(_collector(), [FetchRequest()])
    assert first.accepted == 1
    assert second.accepted == 0
    assert second.skipped_duplicates == 1
    assert len(list_raw_records(seed_session, source_id="example_co")) == 1
