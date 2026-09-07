"""Offline tests for the Adzuna collector + ingest service.

No real network calls — httpx is stubbed with MockTransport.
"""

from __future__ import annotations

import logging

import httpx
import pytest

from collectors.adzuna import AdzunaCollector, CollectorError
from collectors.base import FetchRequest, HealthStatus
from collectors.ingest import ingest_source
from collectors.source_registry import get_registry
from database.models import RawSourceRecord
from database.raw_repository import list_raw_records

SOURCE = get_registry().get("adzuna")


def _job(i: int) -> dict:
    return {
        "id": f"job-{i}",
        "title": f"Senior Java Engineer {i}",
        "description": "Hiring Java and AWS engineers for a modernization project.",
        "company": {"display_name": "ABC Technologies Pvt Ltd"},
        "location": {"display_name": "Bengaluru, India"},
        "category": {"label": "IT Jobs"},
        "created": "2026-09-01T10:00:00Z",
        "redirect_url": f"https://synthetic.example/jobs/{i}",
        "salary_min": 1500000,
        "salary_max": 2500000,
    }


def _client(handler) -> httpx.Client:
    return httpx.Client(transport=httpx.MockTransport(handler))


def _ok_handler(count=2):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"count": count, "results": [_job(1), _job(2)]})

    return handler


@pytest.fixture(autouse=True)
def _creds(monkeypatch):
    monkeypatch.setenv("SOURCE_ADZUNA_APP_ID", "test-app-id")
    monkeypatch.setenv("SOURCE_ADZUNA_API_KEY", "test-app-key")
    monkeypatch.setenv("SOURCE_ADZUNA_COUNTRY", "gb")


def test_fetch_maps_jobs_to_drafts():
    collector = AdzunaCollector(SOURCE, client=_client(_ok_handler(count=2)), sleep=lambda s: None)
    result = collector.fetch(FetchRequest(query="java", limit=20))
    assert result.records_count == 2
    rec = result.records[0]
    assert rec.source_id == "adzuna"
    assert rec.external_id == "job-1"
    assert rec.company_name == "ABC Technologies Pvt Ltd"
    assert rec.normalized_company_name == "abc technologies"
    assert rec.record_type == "JOB_POSTING"
    assert rec.is_synthetic is False
    assert rec.published_at is not None
    assert rec.salary == "1500000-2500000"
    assert rec.content_hash and len(rec.content_hash) == 64
    # Collector only collects — normalization (tech/roles) is downstream.
    assert rec.technologies == [] and rec.roles == []


def test_pagination_flags():
    # count=100, per_page=20, page=1 -> has_more, next_cursor=2
    collector = AdzunaCollector(SOURCE, client=_client(_ok_handler(count=100)), sleep=lambda s: None)
    result = collector.fetch(FetchRequest(page=1, limit=20))
    assert result.has_more is True
    assert result.next_cursor == "2"
    assert result.total_records == 100


def test_fetch_requires_credentials(monkeypatch):
    monkeypatch.delenv("SOURCE_ADZUNA_APP_ID", raising=False)
    collector = AdzunaCollector(SOURCE, client=_client(_ok_handler()), sleep=lambda s: None)
    with pytest.raises(CollectorError):
        collector.fetch()


def test_health_check_not_configured(monkeypatch):
    monkeypatch.delenv("SOURCE_ADZUNA_API_KEY", raising=False)
    collector = AdzunaCollector(SOURCE, client=_client(_ok_handler()))
    assert collector.health_check().status == HealthStatus.NOT_CONFIGURED


def test_health_check_healthy():
    collector = AdzunaCollector(SOURCE, client=_client(_ok_handler()), sleep=lambda s: None)
    assert collector.health_check().status == HealthStatus.HEALTHY


def test_retries_transient_then_succeeds():
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        if calls["n"] == 1:
            return httpx.Response(503)
        return httpx.Response(200, json={"count": 1, "results": [_job(1)]})

    collector = AdzunaCollector(SOURCE, client=_client(handler), sleep=lambda s: None)
    result = collector.fetch()
    assert result.records_count == 1
    assert calls["n"] == 2  # retried once


def test_does_not_retry_auth_failure():
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return httpx.Response(401)

    collector = AdzunaCollector(SOURCE, client=_client(handler), sleep=lambda s: None)
    with pytest.raises(CollectorError):
        collector.fetch()
    assert calls["n"] == 1  # 401 is not retryable


def test_incremental_adds_date_filter():
    from datetime import datetime, timedelta, timezone

    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["params"] = dict(request.url.params)
        return httpx.Response(200, json={"count": 0, "results": []})

    collector = AdzunaCollector(SOURCE, client=_client(handler), sleep=lambda s: None)
    since = datetime.now(timezone.utc) - timedelta(days=7)
    collector.fetch_incremental(FetchRequest(since=since))
    assert "max_days_old" in captured["params"]


def test_credentials_not_logged(caplog):
    collector = AdzunaCollector(SOURCE, client=_client(_ok_handler()), sleep=lambda s: None)
    with caplog.at_level(logging.INFO, logger="collectors"):
        collector.fetch(FetchRequest(query="java"))
    assert "test-app-key" not in caplog.text
    assert "test-app-id" not in caplog.text


def test_ingest_persists_and_dedupes(db_session):
    collector = AdzunaCollector(SOURCE, client=_client(_ok_handler(count=2)), sleep=lambda s: None)

    first = ingest_source(collector, db_session, FetchRequest(query="java"))
    assert first.fetched == 2 and first.created == 2 and first.skipped_duplicates == 0

    second = ingest_source(collector, db_session, FetchRequest(query="java"))
    assert second.created == 0 and second.skipped_duplicates == 2

    rows = list_raw_records(db_session, source_id="adzuna")
    assert len(rows) == 2
    assert all(r.is_synthetic is False for r in rows)
    assert db_session.query(RawSourceRecord).count() == 2
