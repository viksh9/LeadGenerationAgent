"""Offline unit tests for the company career-page collector.

No network by default: HTTP is served by httpx.MockTransport and robots.txt via
an injected fetcher. The opt-in live test at the bottom is skipped unless
CAREER_PAGE_INTEGRATION_TEST is truthy and a URL is provided.
"""

from __future__ import annotations

import os

import httpx
import pytest

from collectors.base import FetchRequest, HealthStatus
from collectors.company.career_page import CareerPageCollector
from collectors.company.config import CareerCollectorConfig
from collectors.company.http_client import CareerCollectorError, RestrictedError, SafeHttpClient
from collectors.company.mapping import map_job
from collectors.company.parsers import EmbeddedJsonParser, HtmlJobParser, JsonLdParser, parse_jobs
from collectors.company.robots import RobotsPolicy
from collectors.company.safety import SafetyError, is_public_ip, validate_public_url
from collectors.company.sources import (
    CareerSourceDefinition,
    CareerSourceStatus,
    RobotsStatus,
    TermsStatus,
)
from collectors.it_taxonomy import NOT_RELEVANT, RELEVANT, UNKNOWN, classify_it_relevance
from tests.fixtures import career_pages as fx

BASE = "https://careers.example.com/careers"


def _source(**overrides) -> CareerSourceDefinition:
    data = dict(
        source_id="example_co",
        company_name="Example Co",
        company_domain="example.com",
        career_url=BASE,
        enabled=True,
        terms_status=TermsStatus.ALLOWED,
        robots_status=RobotsStatus.ALLOWED,
        status=CareerSourceStatus.REQUIRES_REVIEW,
        country="IN",
        industry="Software",
    )
    data.update(overrides)
    return CareerSourceDefinition(**data)


def _mock_client(handler) -> httpx.Client:
    return httpx.Client(transport=httpx.MockTransport(handler), follow_redirects=False)


def _collector(handler, *, source=None, config=None, robots_txt="User-agent: *\nAllow: /"):
    http = _mock_client(handler)
    src = source or _source()
    robots = RobotsPolicy(lambda url: robots_txt, user_agent="test-agent")
    return CareerPageCollector(
        src, config=config, http=http, robots=robots, sleep=lambda *_: None, resolve_hosts=False
    )


# --------------------------------------------------------------------------- #
# Safety / SSRF
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("url", [
    "http://localhost/careers",
    "http://127.0.0.1/careers",
    "http://10.0.0.5/x",
    "http://192.168.1.10/x",
    "http://169.254.169.254/latest/meta-data/",  # cloud metadata
    "http://[::1]/x",
    "ftp://example.com/x",                        # bad scheme
    "https://foo.internal/x",
    "not-a-url",
])
def test_validate_public_url_blocks_unsafe(url):
    with pytest.raises(SafetyError):
        validate_public_url(url, resolve=False)


def test_validate_public_url_allows_public():
    assert validate_public_url("https://careers.example.com/jobs", resolve=False) == "careers.example.com"
    assert validate_public_url("http://8.8.8.8/x", resolve=False) == "8.8.8.8"


def test_is_public_ip():
    assert is_public_ip("8.8.8.8") is True
    assert is_public_ip("127.0.0.1") is False
    assert is_public_ip("169.254.169.254") is False


def test_private_host_allowlist_permits_local_testing():
    url = "http://127.0.0.1:8000/careers"
    assert validate_public_url(url, allow_private=True) == "127.0.0.1"
    assert validate_public_url(url, allowlisted_hosts=("127.0.0.1",)) == "127.0.0.1"


# --------------------------------------------------------------------------- #
# Parsers
# --------------------------------------------------------------------------- #
def test_jsonld_single_full_mapping():
    jobs = JsonLdParser().parse_jobs(fx.JSONLD_SINGLE, base_url=BASE)
    assert len(jobs) == 1
    job = jobs[0]
    assert job["title"] == "Senior Java Developer"
    assert job["company"] == "Globex Tech"
    assert job["company_domain"] == "globex.example"
    assert job["location"] == "Bengaluru, KA, IN"
    assert job["employment_type"] == "FULL_TIME"
    assert job["date_posted"] == "2026-08-15"
    assert job["identifier"] == "REQ-101"
    assert "INR" in job["salary"] and "1500000-2500000" in job["salary"]
    assert job["url"] == "https://careers.example.com/jobs/senior-java-developer"


def test_jsonld_graph_missing_salary():
    jobs = JsonLdParser().parse_jobs(fx.JSONLD_GRAPH, base_url=BASE)
    assert len(jobs) == 1  # WebSite node ignored
    assert jobs[0]["salary"] is None
    assert jobs[0]["title"] == "Python Data Engineer"


def test_jsonld_remote_and_no_date():
    job = JsonLdParser().parse_jobs(fx.JSONLD_REMOTE, base_url=BASE)[0]
    assert job["remote"] is True
    assert job["date_posted"] is None


def test_jsonld_hybrid_location_preserved():
    job = JsonLdParser().parse_jobs(fx.JSONLD_HYBRID, base_url=BASE)[0]
    assert job["location"] == "Hyderabad, IN"


def test_embedded_json_parser():
    jobs = EmbeddedJsonParser().parse_jobs(fx.EMBEDDED_JSON, base_url=BASE)
    titles = {j["title"] for j in jobs}
    assert "Backend Engineer" in titles
    assert "QA Automation Engineer" in titles
    be = next(j for j in jobs if j["title"] == "Backend Engineer")
    assert be["url"] == "https://boards.example/jobs/be-1"


def test_html_anchor_parser_lowfi():
    jobs = HtmlJobParser().parse_jobs(fx.HTML_ANCHORS, base_url=BASE)
    titles = {j["title"] for j in jobs}
    assert "Cloud Engineer" in titles
    assert "Site Reliability Engineer" in titles
    assert "About us" not in titles  # non-job anchor ignored


def test_parse_jobs_prefers_jsonld():
    result = parse_jobs(fx.JSONLD_SINGLE, base_url=BASE)
    assert result.method == "json-ld"
    assert len(result.jobs) == 1


def test_parse_jobs_falls_back_to_embedded_json():
    result = parse_jobs(fx.EMBEDDED_JSON, base_url=BASE)
    assert result.method == "embedded-json"


def test_pagination_detection():
    result = parse_jobs(fx.LISTING_PAGE1, base_url=BASE)
    assert result.next_url == "https://careers.example.com/careers?page=2"


def test_malformed_html_still_parses_jsonld():
    result = parse_jobs(fx.MALFORMED, base_url=BASE)  # must not raise
    assert any(j["title"] == "AI Engineer" for j in result.jobs)


def test_sparse_job_missing_salary_and_date():
    job = JsonLdParser().parse_jobs(fx.JSONLD_SPARSE, base_url=BASE)[0]
    assert job["salary"] is None
    assert job["date_posted"] is None
    assert job["title"] == "SDET"


# --------------------------------------------------------------------------- #
# Relevance + mapping
# --------------------------------------------------------------------------- #
def test_relevance_classification():
    assert classify_it_relevance("Senior Java Developer") == RELEVANT
    assert classify_it_relevance("Front Desk Receptionist", "greet visitors") == NOT_RELEVANT
    assert classify_it_relevance("Program Coordinator", "coordinate schedules") == UNKNOWN


def test_map_job_extracts_tech_roles_and_relevance():
    job = JsonLdParser().parse_jobs(fx.JSONLD_SINGLE, base_url=BASE)[0]
    draft = map_job(job, _source(), method="json-ld")
    assert draft.source_id == "example_co"
    assert draft.external_id == "REQ-101"
    assert draft.company_name == "Globex Tech"
    assert draft.company_domain == "globex.example"
    assert "Java" in draft.technologies
    assert "AWS" in draft.technologies
    assert draft.record_type == "JOB_POSTING"
    assert draft.is_synthetic is False
    assert draft.published_at is not None
    assert draft.raw_payload["it_relevance"] == RELEVANT
    assert "html" not in draft.raw_payload  # no raw HTML stored


def test_map_nonit_job_tagged_not_relevant_but_retained():
    job = JsonLdParser().parse_jobs(fx.JSONLD_NONIT, base_url=BASE)[0]
    draft = map_job(job, _source(), method="json-ld")
    assert draft.raw_payload["it_relevance"] == NOT_RELEVANT  # retained, not dropped
    assert draft.title == "Front Desk Receptionist"


def test_map_job_falls_back_to_source_company():
    job = {"title": "Engineer", "url": "/jobs/eng"}
    draft = map_job(job, _source(company_name="Example Co"), method="html")
    assert draft.company_name == "Example Co"
    assert draft.external_id == "jobs/eng"  # from URL path


# --------------------------------------------------------------------------- #
# SafeHttpClient behaviour
# --------------------------------------------------------------------------- #
def _html_response(body, ctype="text/html"):
    return httpx.Response(200, headers={"content-type": ctype}, text=body)


def _client(handler, **cfg):
    config = CareerCollectorConfig(requests_per_minute=0, **cfg)
    return SafeHttpClient(config, http=_mock_client(handler), sleep=lambda *_: None)


def test_client_fetches_html():
    page = _client(lambda r: _html_response("<html>ok</html>")).fetch(BASE)
    assert page.status == 200
    assert "ok" in page.text


def test_client_rejects_unsupported_content_type():
    with pytest.raises(CareerCollectorError):
        _client(lambda r: httpx.Response(200, headers={"content-type": "image/png"}, content=b"\x89PNG")).fetch(BASE)


def test_client_403_raises_restricted():
    with pytest.raises(RestrictedError):
        _client(lambda r: httpx.Response(403, text="no")).fetch(BASE)


def test_client_404_not_retried():
    calls = {"n": 0}

    def handler(r):
        calls["n"] += 1
        return httpx.Response(404, text="missing")

    with pytest.raises(CareerCollectorError):
        _client(handler).fetch(BASE)
    assert calls["n"] == 1


def test_client_retries_5xx_then_succeeds():
    calls = {"n": 0}

    def handler(r):
        calls["n"] += 1
        if calls["n"] < 3:
            return httpx.Response(503, text="down")
        return _html_response("<html>ok</html>")

    assert _client(handler).fetch(BASE).status == 200
    assert calls["n"] == 3


def test_client_429_retry_after():
    calls = {"n": 0}
    waited = []

    def handler(r):
        calls["n"] += 1
        if calls["n"] == 1:
            return httpx.Response(429, headers={"Retry-After": "5"}, text="slow")
        return _html_response("<html>ok</html>")

    config = CareerCollectorConfig(requests_per_minute=0)
    client = SafeHttpClient(config, http=_mock_client(handler), sleep=lambda s: waited.append(s))
    client.fetch(BASE)
    assert 5.0 in waited


def test_client_follows_validated_redirect():
    def handler(r):
        if r.url.path == "/careers":
            return httpx.Response(301, headers={"location": "https://careers.example.com/jobs"})
        return _html_response("<html>final</html>")

    page = _client(handler).fetch(BASE)
    assert page.url == "https://careers.example.com/jobs"
    assert "final" in page.text


def test_client_blocks_redirect_to_private_host():
    def handler(r):
        return httpx.Response(302, headers={"location": "http://169.254.169.254/latest/meta-data/"})

    with pytest.raises(SafetyError):
        _client(handler).fetch(BASE)


def test_client_enforces_max_redirects():
    def handler(r):
        # always redirect to a new public path
        n = r.url.path.count("/")
        return httpx.Response(302, headers={"location": f"https://careers.example.com/a{n}/b"})

    with pytest.raises(CareerCollectorError):
        _client(handler, max_redirects=2).fetch(BASE)


def test_client_enforces_max_response_size():
    big = "x" * 5000

    def handler(r):
        return httpx.Response(200, headers={"content-type": "text/html"}, text=big)

    with pytest.raises(CareerCollectorError):
        _client(handler, max_response_size_mb=0.000001).fetch(BASE)


# --------------------------------------------------------------------------- #
# Robots policy
# --------------------------------------------------------------------------- #
def test_robots_allowed():
    policy = RobotsPolicy(lambda url: "User-agent: *\nAllow: /", user_agent="ua")
    assert policy.check("https://x.example/careers") == RobotsStatus.ALLOWED


def test_robots_disallowed():
    policy = RobotsPolicy(lambda url: "User-agent: *\nDisallow: /careers", user_agent="ua")
    assert policy.check("https://x.example/careers/job") == RobotsStatus.DISALLOWED


def test_robots_unknown_when_missing():
    policy = RobotsPolicy(lambda url: None, user_agent="ua")
    assert policy.check("https://x.example/careers") == RobotsStatus.UNKNOWN


# --------------------------------------------------------------------------- #
# Collector end-to-end (mocked)
# --------------------------------------------------------------------------- #
def _listing_handler(r):
    path = r.url.path
    query = r.url.query.decode() if isinstance(r.url.query, bytes) else r.url.query
    if path.endswith("/robots.txt"):
        return httpx.Response(200, headers={"content-type": "text/plain"}, text="User-agent: *\nAllow: /")
    if "page=2" in (query or ""):
        return _html_response(fx.LISTING_PAGE2)
    return _html_response(fx.LISTING_PAGE1)


def test_collector_fetch_paginates_and_maps():
    config = CareerCollectorConfig(requests_per_minute=0, max_pages=2)
    collector = _collector(_listing_handler, config=config)
    result = collector.fetch(FetchRequest(page=2))
    assert result.context["pages_fetched"] == 2
    assert result.context["records_accepted"] == 3
    titles = {d.title for d in result.records}
    assert titles == {"Java Developer", "React Developer", "Platform Engineer"}


def test_collector_dedups_within_batch():
    def handler(r):
        if r.url.path.endswith("/robots.txt"):
            return httpx.Response(200, headers={"content-type": "text/plain"}, text="User-agent: *\nAllow: /")
        return _html_response(fx.JSONLD_DUPLICATE)

    result = _collector(handler).fetch()
    assert result.context["records_accepted"] == 1
    assert result.context["duplicates"] == 1


def test_collector_refuses_when_robots_disallows():
    collector = _collector(_listing_handler, robots_txt="User-agent: *\nDisallow: /")
    with pytest.raises(RestrictedError):
        collector.fetch()


def test_collector_refuses_restricted_terms():
    collector = _collector(_listing_handler, source=_source(terms_status=TermsStatus.RESTRICTED))
    with pytest.raises(RestrictedError):
        collector.fetch()


def test_collector_refuses_js_only():
    collector = _collector(_listing_handler, source=_source(requires_js=True))
    with pytest.raises(CareerCollectorError):
        collector.fetch()


def test_collector_incremental_filters_old_by_date():
    from datetime import datetime, timezone

    config = CareerCollectorConfig(requests_per_minute=0, max_pages=1)
    collector = _collector(_listing_handler, config=config)
    # since in the future → all dated jobs filtered as old
    req = FetchRequest(since=datetime(2099, 1, 1, tzinfo=timezone.utc))
    result = collector.fetch(req)
    assert result.context["records_accepted"] == 0
    assert result.context["records_skipped"] >= 1


# --------------------------------------------------------------------------- #
# Health check
# --------------------------------------------------------------------------- #
def test_health_healthy():
    assert _collector(_listing_handler).health_check().status == HealthStatus.HEALTHY


def test_health_not_configured():
    collector = _collector(_listing_handler, source=_source(career_url=None))
    assert collector.health_check().status == HealthStatus.NOT_CONFIGURED


def test_health_restricted_by_terms():
    collector = _collector(_listing_handler, source=_source(terms_status=TermsStatus.RESTRICTED))
    assert collector.health_check().status == HealthStatus.RESTRICTED


def test_health_restricted_by_robots():
    collector = _collector(_listing_handler, robots_txt="User-agent: *\nDisallow: /")
    assert collector.health_check().status == HealthStatus.RESTRICTED


def test_health_degraded_when_requires_js():
    collector = _collector(_listing_handler, source=_source(requires_js=True))
    assert collector.health_check().status == HealthStatus.DEGRADED


# --------------------------------------------------------------------------- #
# Registry
# --------------------------------------------------------------------------- #
def test_registry_examples_are_not_connected():
    from collectors.company.sources import get_career_registry

    for src in get_career_registry().all():
        assert src.status != CareerSourceStatus.CONNECTED
        assert src.enabled is False
        assert src.is_collectable is False


# --------------------------------------------------------------------------- #
# Opt-in live integration test (skipped by default)
# --------------------------------------------------------------------------- #
@pytest.mark.skipif(
    os.environ.get("CAREER_PAGE_INTEGRATION_TEST", "false").lower() not in {"1", "true", "yes"}
    or not os.environ.get("CAREER_PAGE_TEST_URL"),
    reason="CAREER_PAGE_INTEGRATION_TEST not enabled or CAREER_PAGE_TEST_URL not set",
)
def test_live_career_page_smoke():
    url = os.environ["CAREER_PAGE_TEST_URL"]
    source = _source(source_id="live", career_url=url, robots_status=RobotsStatus.UNKNOWN)
    collector = CareerPageCollector(source, resolve_hosts=True)
    health = collector.health_check()
    assert health.status in {HealthStatus.HEALTHY, HealthStatus.DEGRADED, HealthStatus.RESTRICTED, HealthStatus.UNAVAILABLE}
