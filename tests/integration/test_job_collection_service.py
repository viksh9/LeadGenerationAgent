"""Integration tests for JobCollectionService (persist + dedup + last_seen).

Offline: the collector's HTTP layer is served by httpx.MockTransport, and records
are persisted into a throwaway SQLite DB via the `seed_session` fixture.
"""

from __future__ import annotations

import httpx

from collectors.base import FetchRequest
from collectors.jobs.adzuna import AdzunaJobCollector
from collectors.jobs.config import AdzunaConfig
from collectors.service import JobCollectionService
from collectors.source_registry import get_registry
from database.raw_repository import find_by_external_id, list_raw_records


def _job(**overrides):
    item = {
        "id": "999",
        "title": "Senior Python Engineer",
        "description": "Python, Django and AWS backend engineering.",
        "created": "2026-09-01T10:00:00Z",
        "redirect_url": "https://www.adzuna.in/details/999",
        "company": {"display_name": "Globex Software"},
        "location": {"display_name": "Hyderabad, Telangana"},
        "category": {"label": "IT Jobs"},
    }
    item.update(overrides)
    return item


def _collector(handler):
    http = httpx.Client(transport=httpx.MockTransport(handler))
    config = AdzunaConfig(app_id="i", app_key="k", country="in", requests_per_minute=0)
    return AdzunaJobCollector(get_registry().get("adzuna"), config=config, http=http, sleep=lambda *_: None)


def test_collect_persists_raw_records(seed_session):
    def handler(request):
        return httpx.Response(200, json={"results": [_job(id="1"), _job(id="2")], "count": 2})

    collector = _collector(handler)
    service = JobCollectionService(seed_session)
    summary = service.collect(collector, [FetchRequest(query="python", limit=5)])

    assert summary.fetched == 2
    assert summary.accepted == 2
    assert summary.skipped_duplicates == 0
    stored = list_raw_records(seed_session, source_id="adzuna")
    assert len(stored) == 2
    assert all(r.last_seen_at is not None for r in stored)
    assert all(r.is_synthetic is False for r in stored)


def test_collect_dedups_by_external_id_and_updates_last_seen(seed_session):
    def handler(request):
        return httpx.Response(200, json={"results": [_job(id="1")], "count": 1})

    collector = _collector(handler)
    service = JobCollectionService(seed_session)

    first = service.collect(collector, [FetchRequest(query="python", limit=5)])
    assert first.accepted == 1
    original = find_by_external_id(seed_session, "adzuna", "1")
    first_seen = original.last_seen_at

    # Second run over the same job: no new record, last_seen refreshed.
    second = service.collect(collector, [FetchRequest(query="python", limit=5)])
    assert second.accepted == 0
    assert second.skipped_duplicates == 1
    assert len(list_raw_records(seed_session, source_id="adzuna")) == 1
    refreshed = find_by_external_id(seed_session, "adzuna", "1")
    assert refreshed.last_seen_at >= first_seen


def test_collect_dry_run_does_not_persist(seed_session):
    def handler(request):
        return httpx.Response(200, json={"results": [_job(id="1")], "count": 1})

    service = JobCollectionService(seed_session)
    summary = service.collect(_collector(handler), [FetchRequest(query="python", limit=5)], dry_run=True)
    assert summary.fetched == 1
    assert summary.accepted == 1  # would-be accepted
    assert list_raw_records(seed_session, source_id="adzuna") == []


def test_collect_records_errors_without_aborting(seed_session):
    def handler(request):
        # The "bad" query always fails (exhausts retries -> CollectorError); the
        # "good" query succeeds. Keyed on the query so retries don't cross over.
        if request.url.params.get("what") == "bad":
            return httpx.Response(500, json={})
        return httpx.Response(200, json={"results": [_job(id="ok")], "count": 1})

    collector = _collector(handler)
    service = JobCollectionService(seed_session)
    summary = service.collect(
        collector,
        [FetchRequest(query="bad", limit=5), FetchRequest(query="good", limit=5)],
    )
    assert summary.errors  # the failing request was recorded
    assert summary.accepted == 1  # the second request still persisted
