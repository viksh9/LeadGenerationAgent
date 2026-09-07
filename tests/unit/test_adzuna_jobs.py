"""Offline unit tests for the Adzuna job collector.

No network by default: every HTTP interaction is served by httpx.MockTransport.
The opt-in integration test at the bottom is skipped unless ADZUNA_INTEGRATION_TEST
is truthy AND real credentials are present.
"""

from __future__ import annotations

import os

import httpx
import pytest

from collectors.base import FetchRequest, HealthStatus
from collectors.jobs.adzuna import AdzunaJobCollector
from collectors.jobs.client import AdzunaClient, CollectorError
from collectors.jobs.config import AdzunaConfig
from collectors.jobs.mapping import is_it_relevant, job_warnings, map_job
from collectors.source_registry import get_registry


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def _job(**overrides):
    item = {
        "id": "12345",
        "title": "Senior Java Developer",
        "description": "Building microservices with Java, Spring Boot and AWS.",
        "created": "2026-09-01T10:00:00Z",
        "redirect_url": "https://www.adzuna.in/details/12345",
        "company": {"display_name": "Acme Technologies Pvt Ltd"},
        "location": {"display_name": "Bengaluru, Karnataka", "area": ["India", "Karnataka", "Bengaluru"]},
        "category": {"label": "IT Jobs", "tag": "it-jobs"},
        "salary_min": 1500000,
        "salary_max": 2500000,
        "contract_time": "full_time",
    }
    item.update(overrides)
    return item


def _payload(results, count=None):
    return {"results": results, "count": count if count is not None else len(results)}


def _configured():
    return AdzunaConfig(app_id="test-id", app_key="test-key", country="in", requests_per_minute=0)


def _collector(handler, *, config=None, sleep=None, source_id="adzuna"):
    """Build a collector whose client talks to a MockTransport (no real network)."""
    transport = httpx.MockTransport(handler)
    http = httpx.Client(transport=transport)
    source = get_registry().get(source_id)
    calls = {"sleeps": []}

    def _sleep(seconds):
        calls["sleeps"].append(seconds)

    collector = AdzunaJobCollector(
        source,
        config=config or _configured(),
        http=http,
        sleep=sleep or _sleep,
    )
    collector._sleep_calls = calls["sleeps"]  # for assertions
    return collector


# --------------------------------------------------------------------------- #
# Mapping
# --------------------------------------------------------------------------- #
def test_map_job_maps_core_fields():
    draft = map_job(_job(), country="in", query="Java Developer", location="Bengaluru")
    assert draft.source_id == "adzuna"
    assert draft.external_id == "12345"
    assert draft.source_url == "https://www.adzuna.in/details/12345"
    assert draft.title == "Senior Java Developer"
    assert draft.company_name == "Acme Technologies Pvt Ltd"
    assert draft.normalized_company_name == "acme technologies"
    assert draft.location == "Bengaluru, Karnataka"
    assert draft.industry == "IT Jobs"
    assert draft.contract_type == "full_time"
    assert draft.record_type == "JOB_POSTING"
    assert draft.is_synthetic is False
    assert draft.published_at is not None
    assert draft.content_hash  # auto-derived
    # Collection context preserved alongside the raw payload (no credentials).
    assert draft.raw_payload["_collection"]["query"] == "Java Developer"
    assert draft.raw_payload["_collection"]["country"] == "in"


def test_map_job_salary_and_predicted_flag():
    assert map_job(_job(), country="in").salary == "1500000-2500000"
    predicted = map_job(_job(salary_is_predicted="1"), country="in").salary
    assert predicted == "1500000-2500000 (predicted)"
    none_salary = map_job(_job(salary_min=None, salary_max=None), country="in").salary
    assert none_salary is None


def test_map_job_tolerates_missing_fields():
    draft = map_job({"title": "Backend Engineer"}, country="in")
    assert draft.external_id is None
    assert draft.company_name is None
    assert draft.source_url is None
    assert draft.title == "Backend Engineer"
    assert draft.content_hash  # still derivable


def test_content_hash_stable_across_intraday_recollection():
    a = map_job(_job(created="2026-09-01T10:00:00Z"), country="in")
    b = map_job(_job(created="2026-09-01T23:59:00Z"), country="in")
    assert a.content_hash == b.content_hash  # date-only in hash


def test_content_hash_differs_for_different_jobs():
    a = map_job(_job(id="1"), country="in")
    b = map_job(_job(id="2"), country="in")
    assert a.content_hash != b.content_hash


# --------------------------------------------------------------------------- #
# IT relevance + quality warnings
# --------------------------------------------------------------------------- #
def test_is_it_relevant_keeps_it_roles():
    assert is_it_relevant(_job()) is True
    assert is_it_relevant({"title": "Cloud Engineer", "description": ""}) is True


def test_is_it_relevant_drops_obvious_non_it():
    assert is_it_relevant({"title": "Chef de Partie", "description": "kitchen work",
                           "category": {"label": "Catering Jobs"}}) is False


def test_job_warnings_flags_missing_fields():
    warnings = job_warnings({"description": "x"})
    assert "missing job id" in warnings
    assert "missing title" in warnings
    assert "missing company name" in warnings
    assert "missing source url" in warnings


def test_job_warnings_clean_record_has_none():
    assert job_warnings(_job()) == []


# --------------------------------------------------------------------------- #
# fetch()
# --------------------------------------------------------------------------- #
def test_fetch_returns_mapped_records():
    def handler(request):
        assert "app_id" in request.url.params
        assert request.url.params["what"] == "Java Developer"
        return httpx.Response(200, json=_payload([_job(id="1"), _job(id="2")], count=2))

    collector = _collector(handler)
    result = collector.fetch(FetchRequest(query="Java Developer", location="Bengaluru", limit=20))
    assert result.records_count == 2
    assert result.source_id == "adzuna"
    assert result.context["query"] == "Java Developer"
    assert result.context["country"] == "in"
    assert result.duration_seconds is not None


def test_fetch_filters_non_it_records():
    def handler(request):
        return httpx.Response(200, json=_payload([
            _job(id="1"),
            {"id": "2", "title": "Waiter", "description": "restaurant", "category": {"label": "Catering Jobs"}},
        ], count=2))

    result = _collector(handler).fetch(FetchRequest(query="engineer"))
    assert result.records_count == 1
    assert any("filtered 1 non-IT" in w for w in result.warnings)


def test_fetch_signals_has_more_when_more_pages():
    def handler(request):
        return httpx.Response(200, json=_payload([_job(id=str(i)) for i in range(5)], count=50))

    result = _collector(handler).fetch(FetchRequest(query="engineer", page=1, limit=5))
    assert result.has_more is True
    assert result.next_cursor == "2"


def test_fetch_no_more_pages_on_last():
    def handler(request):
        return httpx.Response(200, json=_payload([_job(id="1")], count=1))

    result = _collector(handler).fetch(FetchRequest(query="engineer", page=1, limit=5))
    assert result.has_more is False
    assert result.next_cursor is None


def test_fetch_handles_malformed_response():
    def handler(request):
        return httpx.Response(200, json={"unexpected": "shape"})

    result = _collector(handler).fetch(FetchRequest(query="engineer"))
    assert result.records_count == 0  # no crash, empty batch


def test_fetch_raises_when_not_configured():
    def handler(request):  # pragma: no cover - should never be called
        raise AssertionError("no HTTP call expected when unconfigured")

    unconfigured = AdzunaConfig(app_id=None, app_key=None)
    collector = _collector(handler, config=unconfigured)
    with pytest.raises(CollectorError):
        collector.fetch(FetchRequest(query="engineer"))


def test_fetch_respects_country_config():
    seen = {}

    def handler(request):
        seen["path"] = request.url.path
        return httpx.Response(200, json=_payload([_job()]))

    config = AdzunaConfig(app_id="i", app_key="k", country="gb", requests_per_minute=0)
    _collector(handler, config=config).fetch(FetchRequest(query="engineer"))
    assert "/jobs/gb/search/" in seen["path"]


# --------------------------------------------------------------------------- #
# Retry / rate-limit behaviour (client)
# --------------------------------------------------------------------------- #
def test_retries_transient_5xx_then_succeeds():
    attempts = {"n": 0}

    def handler(request):
        attempts["n"] += 1
        if attempts["n"] < 3:
            return httpx.Response(503, json={"error": "unavailable"})
        return httpx.Response(200, json=_payload([_job()]))

    collector = _collector(handler)
    result = collector.fetch(FetchRequest(query="engineer"))
    assert attempts["n"] == 3
    assert result.records_count == 1


def test_429_honours_retry_after():
    attempts = {"n": 0}

    def handler(request):
        attempts["n"] += 1
        if attempts["n"] == 1:
            return httpx.Response(429, headers={"Retry-After": "7"}, json={})
        return httpx.Response(200, json=_payload([_job()]))

    collector = _collector(handler)
    collector.fetch(FetchRequest(query="engineer"))
    assert 7.0 in collector._sleep_calls  # honoured the header


def test_does_not_retry_non_transient_4xx():
    attempts = {"n": 0}

    def handler(request):
        attempts["n"] += 1
        return httpx.Response(400, json={"error": "bad request"})

    collector = _collector(handler)
    with pytest.raises(CollectorError):
        collector.fetch(FetchRequest(query="engineer"))
    assert attempts["n"] == 1  # no retry on 400


def test_auth_failure_not_retried():
    attempts = {"n": 0}

    def handler(request):
        attempts["n"] += 1
        return httpx.Response(401, json={"error": "unauthorized"})

    with pytest.raises(CollectorError):
        _collector(handler).fetch(FetchRequest(query="engineer"))
    assert attempts["n"] == 1


# --------------------------------------------------------------------------- #
# health_check()
# --------------------------------------------------------------------------- #
def test_health_check_not_configured():
    def handler(request):  # pragma: no cover
        raise AssertionError("no HTTP call when unconfigured")

    collector = _collector(handler, config=AdzunaConfig())
    result = collector.health_check()
    assert result.status == HealthStatus.NOT_CONFIGURED
    # never expose credentials
    assert "test-key" not in (result.message or "")


def test_health_check_healthy():
    def handler(request):
        return httpx.Response(200, json=_payload([_job()]))

    assert _collector(handler).health_check().status == HealthStatus.HEALTHY


def test_health_check_unavailable_on_error():
    def handler(request):
        return httpx.Response(500, json={})

    assert _collector(handler).health_check().status == HealthStatus.UNAVAILABLE


# --------------------------------------------------------------------------- #
# Credential hygiene
# --------------------------------------------------------------------------- #
def test_credentials_never_logged(caplog):
    def handler(request):
        return httpx.Response(200, json=_payload([_job()]))

    config = AdzunaConfig(app_id="SECRET_ID", app_key="SECRET_KEY", country="in", requests_per_minute=0)
    with caplog.at_level("INFO"):
        _collector(handler, config=config).fetch(FetchRequest(query="engineer"))
    blob = "\n".join(r.getMessage() for r in caplog.records)
    assert "SECRET_ID" not in blob
    assert "SECRET_KEY" not in blob


# --------------------------------------------------------------------------- #
# plan_requests()
# --------------------------------------------------------------------------- #
def test_plan_requests_uses_controlled_strategy():
    # ROLE_FIRST (default) is India-wide: one base query per role term (no per-city
    # fan-out), paginated — NOT the old roles×locations×pages cartesian.
    config = AdzunaConfig(
        app_id="i", app_key="k",
        search_terms=["Java Developer", "Python Developer"],
        locations=["Bengaluru", "Pune"],
        search_mode="ROLE_FIRST", max_requests_per_run=30,
    )

    def handler(request):  # pragma: no cover - plan_requests makes no calls
        raise AssertionError("plan_requests should not hit the network")

    collector = _collector(handler, config=config)
    plan = collector.plan_requests(max_pages=2)
    assert len(plan) == 2 * 2                      # 2 terms × 2 pages, India-wide
    assert {r.location for r in plan} == {None}     # no per-city fan-out
    assert all(isinstance(r, FetchRequest) for r in plan)


def test_plan_requests_respects_request_cap():
    config = AdzunaConfig(
        app_id="i", app_key="k",
        search_terms=["a", "b", "c", "d", "e"], locations=["X"],
        max_requests_per_run=3,
    )
    collector = _collector(lambda r: None, config=config)
    assert len(collector.plan_requests(max_pages=2)) == 3


# --------------------------------------------------------------------------- #
# Opt-in live integration test (skipped by default; needs real credentials)
# --------------------------------------------------------------------------- #
@pytest.mark.skipif(
    os.environ.get("ADZUNA_INTEGRATION_TEST", "false").lower() not in {"1", "true", "yes"}
    or not (os.environ.get("ADZUNA_APP_ID") and os.environ.get("ADZUNA_APP_KEY")),
    reason="ADZUNA_INTEGRATION_TEST not enabled or credentials missing",
)
def test_live_adzuna_smoke():
    """Single tiny live call (results_per_page=1) — opt-in only."""
    from collectors.jobs.config import load_adzuna_config

    config = load_adzuna_config()
    source = get_registry().get("adzuna")
    collector = AdzunaJobCollector(source, config=config)
    assert collector.health_check().status == HealthStatus.HEALTHY
    result = collector.fetch(FetchRequest(query="software engineer", limit=1))
    assert result.records_count <= 1
