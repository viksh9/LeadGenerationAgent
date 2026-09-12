"""ContactOut client + mapper tests (Prompt 44).

All offline — the network layer uses httpx.MockTransport; no real ContactOut call
is ever made and no token is required. Verifies auth header (never a query param),
request shapes, defensive parsing (nothing fabricated), and error/rate-limit mapping.
"""

from __future__ import annotations

import httpx
import pytest

from integrations.contactout import (
    ContactOutClient,
    ContactOutConfig,
    parse_enrich,
    parse_people,
)
from integrations.contactout.exceptions import (
    ContactOutAuthError,
    ContactOutBadResponse,
    ContactOutNotConfigured,
    ContactOutRateLimitError,
    ContactOutUnavailableError,
)

CFG = ContactOutConfig(api_token="secret-token", base_url="https://api.contactout.com", max_retries=3)


def _client(handler, *, cfg=CFG):
    return ContactOutClient(cfg, http=httpx.Client(transport=httpx.MockTransport(handler)),
                            sleep=lambda s: None)


# --------------------------------------------------------------------------- #
# Authentication (§2)
# --------------------------------------------------------------------------- #
def test_auth_uses_token_header_never_query():
    seen = {}

    def h(req):
        seen["token"] = req.headers.get("token")
        seen["query"] = str(req.url.query)
        return httpx.Response(200, json={"profiles": []})

    _client(h).get_decision_makers(domain="acme.com")
    assert seen["token"] == "secret-token"
    assert "secret-token" not in seen["query"] and "token" not in seen["query"].lower()


def test_no_token_raises_not_configured_no_call():
    called = {"n": 0}

    def h(req):
        called["n"] += 1
        return httpx.Response(200, json={})

    with pytest.raises(ContactOutNotConfigured):
        _client(h, cfg=ContactOutConfig(api_token=None)).get_decision_makers(domain="acme.com")
    assert called["n"] == 0   # never hit the network


# --------------------------------------------------------------------------- #
# Request shapes (§4/§5/§14)
# --------------------------------------------------------------------------- #
def test_decision_makers_requires_identifier():
    with pytest.raises(ContactOutBadResponse):
        _client(lambda r: httpx.Response(200, json={})).get_decision_makers()


def test_people_search_posts_current_titles_and_company():
    captured = {}

    def h(req):
        import json
        captured.update(json.loads(req.content))
        captured["method"] = req.method
        return httpx.Response(200, json={"profiles": []})

    _client(h).search_people(job_title=["VP Engineering"], company="Acme", location="Bengaluru")
    assert captured["method"] == "POST"
    assert captured["current_titles_only"] is True
    assert captured["company"] == "Acme" and captured["job_title"] == ["VP Engineering"]


def test_enrich_requires_identifier():
    with pytest.raises(ContactOutBadResponse):
        _client(lambda r: httpx.Response(200, json={})).enrich_person()


# --------------------------------------------------------------------------- #
# Mapper — nothing fabricated (§10/§11/§12/§13/§19)
# --------------------------------------------------------------------------- #
def test_mapper_parses_person_and_availability():
    raw = {"profiles": [{
        "full_name": "Jane Doe", "title": "VP Engineering",
        "company": {"name": "Acme", "domain": "acme.com"},
        "linkedin_url": "https://linkedin.com/in/janedoe",
        "work_email": ["jane@acme.com"], "work_email_status": "verified",
        "phone": ["+91-80-1234"], "location": "Bengaluru", "is_current": True}]}
    p = parse_people(raw, endpoint="decision-makers").people[0]
    assert p.full_name == "Jane Doe" and p.job_title == "VP Engineering"
    assert p.work_email == "jane@acme.com" and p.work_email_verified is True
    assert p.phone == "+91-80-1234" and p.linkedin_url == "https://linkedin.com/in/janedoe"
    assert p.availability.work_email and p.availability.phone
    assert p.company_domain == "acme.com" and p.is_current is True


def test_mapper_absent_contact_stays_none():
    raw = {"profiles": [{"full_name": "No Contact", "title": "CTO", "company": "Acme"}]}
    p = parse_people(raw, endpoint="decision-makers").people[0]
    assert p.work_email is None and p.phone is None
    assert not p.availability.work_email and not p.availability.phone


def test_mapper_personal_email_not_promoted_to_work():
    raw = {"profiles": [{"full_name": "P", "personal_email": ["p@gmail.com"]}]}
    p = parse_people(raw, endpoint="decision-makers").people[0]
    assert p.work_email is None and p.personal_email == "p@gmail.com"
    assert p.best_business_email() is None


def test_enrich_returns_none_when_no_profile():
    assert parse_enrich({"profile": None}) is None
    assert parse_enrich({}) is None


# --------------------------------------------------------------------------- #
# Error / rate-limit handling (§26/§27)
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("code", [401, 403])
def test_auth_errors_not_retried(code):
    calls = {"n": 0}

    def h(req):
        calls["n"] += 1
        return httpx.Response(code, json={"error": "no"})

    with pytest.raises(ContactOutAuthError):
        _client(h).get_decision_makers(domain="acme.com")
    assert calls["n"] == 1   # never retried


def test_429_honours_retry_after_then_raises():
    calls = {"n": 0}

    def h(req):
        calls["n"] += 1
        return httpx.Response(429, headers={"Retry-After": "1"})

    with pytest.raises(ContactOutRateLimitError) as ei:
        _client(h, cfg=ContactOutConfig(api_token="t", max_retries=2)).get_decision_makers(domain="acme.com")
    assert calls["n"] == 2 and ei.value.retry_after == 1.0


def test_5xx_retried_then_unavailable():
    calls = {"n": 0}

    def h(req):
        calls["n"] += 1
        return httpx.Response(503)

    with pytest.raises(ContactOutUnavailableError):
        _client(h, cfg=ContactOutConfig(api_token="t", max_retries=2)).get_decision_makers(domain="acme.com")
    assert calls["n"] == 2


def test_400_is_unavailable_not_fabricated():
    with pytest.raises(ContactOutUnavailableError):
        _client(lambda r: httpx.Response(400, json={"error": "bad"})).get_decision_makers(domain="acme.com")


def test_timeout_maps_to_unavailable():
    def h(req):
        raise httpx.ConnectTimeout("boom", request=req)

    with pytest.raises(ContactOutUnavailableError):
        _client(h, cfg=ContactOutConfig(api_token="t", max_retries=1)).get_decision_makers(domain="acme.com")


def test_invalid_json_is_bad_response():
    def h(req):
        return httpx.Response(200, content=b"not-json", headers={"content-type": "application/json"})

    with pytest.raises(ContactOutBadResponse):
        _client(h).get_decision_makers(domain="acme.com")


# --------------------------------------------------------------------------- #
# Connectivity check (§39)
# --------------------------------------------------------------------------- #
def test_check_connection_states():
    from collectors.base import HealthStatus

    assert ContactOutClient(ContactOutConfig(api_token=None)).check_connection()[0] is HealthStatus.NOT_CONFIGURED
    assert _client(lambda r: httpx.Response(200, json={})).check_connection()[0] is HealthStatus.HEALTHY
    assert _client(lambda r: httpx.Response(401)).check_connection()[0] is HealthStatus.AUTHENTICATION_FAILED
    assert _client(lambda r: httpx.Response(429)).check_connection()[0] is HealthStatus.RATE_LIMITED
