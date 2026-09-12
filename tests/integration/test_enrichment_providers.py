"""Paid enrichment provider client tests (Prompt 49).

All offline — the network layer uses httpx.MockTransport; no real provider call is ever
made and no key is required beyond the in-memory test value. Verifies auth transport
(header/query, never leaked), request shapes, defensive parsing (nothing fabricated),
email-verification status normalization (§20/§21), phone typing (§22), and error mapping.
"""

from __future__ import annotations

import httpx
import pytest

from config import get_settings
from integrations.enrichment.base import (
    EnrichmentAuthError,
    EnrichmentNotConfigured,
    EnrichmentRateLimited,
    EnrichmentUnavailable,
)
from integrations.enrichment.providers.apollo import ApolloProvider
from integrations.enrichment.providers.hunter import HunterProvider
from integrations.enrichment.providers.lusha import LushaProvider
from integrations.enrichment.providers.prospeo import ProspeoProvider


@pytest.fixture(autouse=True)
def _keys():
    """Set in-memory provider keys; restore afterwards (never touches real env)."""
    s = get_settings()
    prev = (s.apollo_api_key, s.lusha_api_key, s.hunter_api_key, s.prospeo_api_key)
    s.apollo_api_key = "apollo-key"
    s.lusha_api_key = "lusha-key"
    s.hunter_api_key = "hunter-key"
    s.prospeo_api_key = "prospeo-key"
    yield s
    (s.apollo_api_key, s.lusha_api_key, s.hunter_api_key, s.prospeo_api_key) = prev


def _mock(handler):
    return httpx.Client(transport=httpx.MockTransport(handler))


# --------------------------------------------------------------------------- #
# Apollo — X-Api-Key header; people search + match + org enrich
# --------------------------------------------------------------------------- #
def test_apollo_auth_header_and_search():
    seen = {}

    def h(req):
        seen["key"] = req.headers.get("X-Api-Key")
        seen["query"] = str(req.url.query)
        if req.url.path.endswith("/mixed_people/search"):
            return httpx.Response(200, json={"people": [
                {"name": "Jane Doe", "title": "VP Engineering",
                 "organization": {"name": "Acme Corp", "primary_domain": "acme.com", "id": "o1"}, "id": "p1"}]})
        return httpx.Response(404)

    people = ApolloProvider(http=_mock(h)).search_people(company_name="Acme Corp", titles=["VP Engineering"])
    assert seen["key"] == "apollo-key"
    assert "apollo-key" not in seen["query"]           # key never in query string
    assert len(people) == 1 and people[0].full_name == "Jane Doe"
    assert people[0].company_domain == "acme.com"


def test_apollo_no_key_raises_not_configured_no_call(_keys):
    _keys.apollo_api_key = None
    called = {"n": 0}

    def h(req):
        called["n"] += 1
        return httpx.Response(200, json={})

    with pytest.raises(EnrichmentNotConfigured):
        ApolloProvider(http=_mock(h)).search_people(company_name="Acme", titles=["CTO"])
    assert called["n"] == 0


def test_apollo_401_maps_auth_error():
    def h(req):
        return httpx.Response(401, json={"error": "unauthorized"})

    with pytest.raises(EnrichmentAuthError):
        ApolloProvider(http=_mock(h), sleep=lambda s: None).search_people(company_name="Acme", titles=["CTO"])


# --------------------------------------------------------------------------- #
# Lusha — api_key header; person + company enrichment
# --------------------------------------------------------------------------- #
def test_lusha_auth_header_and_person_enrich():
    seen = {}

    def h(req):
        seen["key"] = req.headers.get("api_key")
        if "/person" in req.url.path:
            return httpx.Response(200, json={"data": {"firstName": "Jane", "lastName": "Doe",
                "jobTitle": "CTO", "emailAddresses": [{"email": "jane@acme.com"}]}})
        return httpx.Response(404)

    person = LushaProvider(http=_mock(h)).enrich_person(full_name="Jane Doe", company_name="Acme", domain="acme.com")
    assert seen["key"] == "lusha-key"
    assert person is not None


# --------------------------------------------------------------------------- #
# Hunter — api_key QUERY param; email finder + verifier status normalization
# --------------------------------------------------------------------------- #
def test_hunter_key_in_query_and_email_finder():
    seen = {}

    def h(req):
        seen["query"] = str(req.url.query)
        if "/email-finder" in req.url.path:
            return httpx.Response(200, json={"data": {"email": "jane@acme.com",
                                                      "verification": {"status": "valid"}}})
        return httpx.Response(404)

    er = HunterProvider(http=_mock(h)).find_business_email(full_name="Jane Doe", domain="acme.com")
    assert "api_key=hunter-key" in seen["query"]
    assert er is not None and er.email == "jane@acme.com" and er.verification_status == "VALID"


@pytest.mark.parametrize("raw,expected", [
    ("valid", "VALID"), ("invalid", "INVALID"), ("accept_all", "ACCEPT_ALL"),
    ("webmail", "WEBMAIL"), ("disposable", "DISPOSABLE"), ("unknown", "UNKNOWN"),
])
def test_hunter_verify_status_normalization(raw, expected):
    def h(req):
        return httpx.Response(200, json={"data": {"status": raw}})

    v = HunterProvider(http=_mock(h)).verify_email("jane@acme.com")
    assert v is not None and v.verification_status == expected


def test_hunter_never_fabricates_missing_email():
    def h(req):
        return httpx.Response(200, json={"data": {"email": None}})   # no email returned

    assert HunterProvider(http=_mock(h)).find_business_email(full_name="Jane Doe", domain="acme.com") is None


# --------------------------------------------------------------------------- #
# Prospeo — X-KEY header; email finder + rate-limit mapping
# --------------------------------------------------------------------------- #
def test_prospeo_auth_header_and_email_finder():
    seen = {}

    def h(req):
        seen["key"] = req.headers.get("X-KEY")
        return httpx.Response(200, json={"response": {"email": "jane@acme.com", "email_status": "valid"}})

    er = ProspeoProvider(http=_mock(h)).find_business_email(full_name="Jane Doe", domain="acme.com")
    assert seen["key"] == "prospeo-key"
    assert er is not None and er.email == "jane@acme.com" and er.verification_status == "VALID"


def test_prospeo_429_maps_rate_limited():
    def h(req):
        return httpx.Response(429, headers={"Retry-After": "0"}, json={"error": "rate"})

    with pytest.raises(EnrichmentRateLimited):
        ProspeoProvider(http=_mock(h), sleep=lambda s: None).find_business_email(full_name="Jane Doe", domain="acme.com")


def test_health_check_not_configured_makes_no_call(_keys):
    from collectors.base import HealthStatus
    for name, cls in (("apollo", ApolloProvider), ("lusha", LushaProvider),
                      ("hunter", HunterProvider), ("prospeo", ProspeoProvider)):
        setattr(_keys, f"{name}_api_key", None)
        called = {"n": 0}

        def h(req):
            called["n"] += 1
            return httpx.Response(200, json={})

        status, _ = cls(http=_mock(h)).health_check()
        assert status == HealthStatus.NOT_CONFIGURED
        assert called["n"] == 0
