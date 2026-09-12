"""Public-intelligence unit tests (Prompt 45) — offline, nothing fabricated.

Covers matching (company match / role relevance), trust scoring (§19), POC status
(§22), RSS/Atom parsing, the shared HTTP client error mapping (429/5xx/timeout/404),
and GitHub/Wikidata provider parsing via httpx.MockTransport.
"""

from __future__ import annotations

import httpx
import pytest

from integrations.public_intelligence.base import ProviderRateLimited, ProviderUnavailable
from integrations.public_intelligence.github import GitHubProvider
from integrations.public_intelligence.http import PublicJsonClient
from integrations.public_intelligence.matching import company_match, role_relevance
from integrations.public_intelligence.models import (
    MATCH_LIKELY,
    MATCH_UNKNOWN,
    MATCH_VERIFIED,
    STATUS_LIKELY,
    STATUS_UNVERIFIED,
    STATUS_VERIFIED,
    CompanyContext,
)
from integrations.public_intelligence.rss import RssClient
from integrations.public_intelligence.trust import compute_contact_trust, poc_status
from integrations.public_intelligence.wikidata import WikidataProvider

CTX = CompanyContext(company_id=1, company_name="Acme Corp", normalized_name="acme corp", domain="acme.com")


# --- matching --------------------------------------------------------------- #
def test_company_match_domain_is_verified():
    st, _ = company_match(company_text=None, blog_or_domain="https://acme.com", ctx=CTX)
    assert st == MATCH_VERIFIED


def test_company_match_self_reported_is_likely():
    st, _ = company_match(company_text="Acme Corp", blog_or_domain=None, ctx=CTX)
    assert st == MATCH_LIKELY


def test_company_match_wrong_company_unknown():
    st, _ = company_match(company_text="Globex", blog_or_domain="https://globex.com", ctx=CTX)
    assert st == MATCH_UNKNOWN


def test_role_relevance_matches_recommended():
    assert role_relevance("VP Engineering", ["VP Engineering", "CTO"]) >= 90
    assert role_relevance("Marketing Manager", ["VP Engineering"]) == 0


# --- trust scoring (§19) ---------------------------------------------------- #
def test_trust_full_official():
    assert compute_contact_trust(official_source=True, current_company_match=True,
                                 current_title_match=True, public_business_email=True,
                                 public_business_phone=True) == 100


def test_trust_partial_points_only_on_evidence():
    # github (not official), company match + title + email, no phone → 25+20+10 = 55
    assert compute_contact_trust(official_source=False, current_company_match=True,
                                 current_title_match=True, public_business_email=True,
                                 public_business_phone=False) == 55
    assert compute_contact_trust(official_source=False, current_company_match=False,
                                 current_title_match=False, public_business_email=False,
                                 public_business_phone=False) == 0


def test_poc_status_states():
    assert poc_status(company_match_status=MATCH_VERIFIED, current_title_match=True) == STATUS_VERIFIED
    assert poc_status(company_match_status=MATCH_LIKELY, current_title_match=False) == STATUS_LIKELY
    assert poc_status(company_match_status=MATCH_UNKNOWN, current_title_match=True) == STATUS_UNVERIFIED


# --- RSS / Atom parsing ----------------------------------------------------- #
def test_rss_parses_items():
    xml = """<rss><channel><item><title>New AI lab</title>
    <link>https://x.com/a</link><pubDate>Mon, 01 Jan 2026</pubDate></item></channel></rss>"""
    entries = RssClient().parse(xml)
    assert len(entries) == 1 and entries[0].title == "New AI lab" and entries[0].link == "https://x.com/a"


def test_atom_parses_entries():
    xml = """<feed xmlns="http://www.w3.org/2005/Atom"><entry><title>Cloud move</title>
    <link href="https://x.com/b"/><updated>2026-01-01</updated></entry></feed>"""
    entries = RssClient().parse(xml)
    assert len(entries) == 1 and entries[0].link == "https://x.com/b"


def test_rss_bad_xml_is_empty_not_error():
    assert RssClient().parse("<not xml") == []


# --- shared HTTP client error mapping --------------------------------------- #
def _pjc(handler):
    return PublicJsonClient(base_url="https://api.test", user_agent="UA", max_retries=2,
                            http=httpx.Client(transport=httpx.MockTransport(handler)),
                            sleep=lambda s: None)


def test_http_404_returns_none():
    assert _pjc(lambda r: httpx.Response(404)).get_json("/x") is None


def test_http_429_raises_rate_limited():
    with pytest.raises(ProviderRateLimited):
        _pjc(lambda r: httpx.Response(429, headers={"Retry-After": "1"})).get_json("/x")


def test_http_5xx_raises_unavailable():
    with pytest.raises(ProviderUnavailable):
        _pjc(lambda r: httpx.Response(503)).get_json("/x")


def test_http_timeout_raises_unavailable():
    def h(req):
        raise httpx.ConnectTimeout("boom", request=req)
    with pytest.raises(ProviderUnavailable):
        _pjc(h).get_json("/x")


# --- provider parsing (mock transport) -------------------------------------- #
def test_github_provider_includes_only_matched_people():
    def h(req):
        if req.url.path == "/search/users":
            return httpx.Response(200, json={"items": [{"login": "ok"}, {"login": "no"}]})
        if req.url.path == "/users/ok":
            return httpx.Response(200, json={"login": "ok", "name": "Jane", "company": "Acme Corp",
                "blog": "https://acme.com", "email": "jane@acme.com", "id": 1,
                "html_url": "https://github.com/ok", "bio": "VP Engineering"})
        if req.url.path == "/users/no":
            return httpx.Response(200, json={"login": "no", "name": "Bob", "company": "Globex",
                "id": 2, "html_url": "https://github.com/no"})
        return httpx.Response(404)
    prov = GitHubProvider(http=httpx.Client(transport=httpx.MockTransport(h)), sleep=lambda s: None)
    res = prov.discover(CTX, ["VP Engineering"])
    assert res.status == "OK" and len(res.people) == 1
    p = res.people[0]
    assert p.full_name == "Jane" and p.company_match_status == MATCH_VERIFIED
    assert p.work_email == "jane@acme.com"   # only because GitHub returned it


def test_github_no_public_email_stays_none():
    def h(req):
        if req.url.path == "/search/users":
            return httpx.Response(200, json={"items": [{"login": "ok"}]})
        return httpx.Response(200, json={"login": "ok", "name": "Jane", "company": "Acme Corp",
            "blog": "https://acme.com", "id": 1, "html_url": "https://github.com/ok"})
    prov = GitHubProvider(http=httpx.Client(transport=httpx.MockTransport(h)), sleep=lambda s: None)
    p = prov.discover(CTX, ["VP Engineering"]).people[0]
    assert p.work_email is None    # never derived


def test_wikidata_provider_resolves_entity():
    def h(req):
        return httpx.Response(200, json={"results": {"bindings": [{
            "item": {"value": "http://www.wikidata.org/entity/Q42"},
            "itemLabel": {"value": "Acme Corp"}, "website": {"value": "https://acme.com"},
            "countryLabel": {"value": "India"}, "industryLabel": {"value": "IT"}}]}})
    prov = WikidataProvider(http=httpx.Client(transport=httpx.MockTransport(h)), sleep=lambda s: None)
    facts = prov.discover(CTX, []).company_facts
    assert facts.wikidata_id == "Q42" and facts.website == "https://acme.com"
    assert facts.source_url == "https://www.wikidata.org/wiki/Q42"


def test_github_org_matched_by_domain():
    def h(req):
        if req.url.path == "/search/users":
            return httpx.Response(200, json={"items": [{"login": "acme"}]})
        if req.url.path == "/orgs/acme":
            return httpx.Response(200, json={"login": "acme", "name": "Acme Corp",
                "blog": "https://acme.com", "html_url": "https://github.com/acme"})
        return httpx.Response(404)
    prov = GitHubProvider(http=httpx.Client(transport=httpx.MockTransport(h)), sleep=lambda s: None)
    facts = prov.discover_company(CTX)   # CTX domain=acme.com
    assert facts is not None and facts.github_url == "https://github.com/acme"
    assert any(e.field == "github_url" for e in facts.field_evidence)


def test_github_org_rejected_on_domain_mismatch():
    def h(req):
        if req.url.path == "/search/users":
            return httpx.Response(200, json={"items": [{"login": "acme"}]})
        if req.url.path == "/orgs/acme":
            return httpx.Response(200, json={"login": "acme", "name": "Acme Corp",
                "blog": "https://different.com", "html_url": "https://github.com/acme"})
        return httpx.Response(404)
    prov = GitHubProvider(http=httpx.Client(transport=httpx.MockTransport(h)), sleep=lambda s: None)
    assert prov.discover_company(CTX) is None   # name matches but domain does not → not matched


def test_provider_error_yields_status_not_fabrication():
    prov = GitHubProvider(http=httpx.Client(transport=httpx.MockTransport(
        lambda r: httpx.Response(500))), sleep=lambda s: None)
    res = prov.discover(CTX, ["VP Engineering"])
    assert res.status in ("UNAVAILABLE", "ERROR") and res.people == []


def test_github_includes_public_org_members_as_verified_pocs():
    """Expansion: PUBLIC members of the company's official GitHub org are authoritative
    employees -> VERIFIED POCs, merged with self-declared profiles and deduped."""
    import json as _json

    def h(req):
        path = req.url.path
        q = req.url.params.get("q", "")
        if path == "/search/users":
            if "type:org" in q:
                return httpx.Response(200, json={"items": [{"login": "acme"}]})
            return httpx.Response(200, json={"items": [{"login": "selfuser"}]})   # self-listed
        if path == "/orgs/acme/public_members":
            return httpx.Response(200, json=[{"login": "eng1"}, {"login": "eng2"}])
        if path == "/orgs/acme":
            return httpx.Response(200, json={"login": "acme", "name": "Acme Corp",
                                             "blog": "https://acme.com", "html_url": "https://github.com/acme"})
        if path == "/users/selfuser":
            return httpx.Response(200, json={"login": "selfuser", "name": "Self Lister",
                "company": "Acme Corp", "blog": "https://acme.com", "id": 9,
                "html_url": "https://github.com/selfuser", "bio": "VP Engineering"})
        if path == "/users/eng1":
            return httpx.Response(200, json={"login": "eng1", "name": "Ravi Kumar", "company": None,
                "id": 1, "html_url": "https://github.com/eng1", "bio": "Staff Software Engineer"})
        if path == "/users/eng2":
            return httpx.Response(200, json={"login": "eng2", "name": "Anita Rao", "company": "@acme",
                "id": 2, "html_url": "https://github.com/eng2"})
        return httpx.Response(404)

    prov = GitHubProvider(http=httpx.Client(transport=httpx.MockTransport(h)), sleep=lambda s: None)
    people = prov.discover_people(CTX, roles=[])
    by_name = {p.full_name: p for p in people}
    assert {"Self Lister", "Ravi Kumar", "Anita Rao"} <= set(by_name)     # self-lister + 2 org members
    # Org members are VERIFIED + marked current (membership is authoritative).
    assert by_name["Ravi Kumar"].company_match_status == MATCH_VERIFIED
    assert by_name["Ravi Kumar"].is_current is True
    assert by_name["Ravi Kumar"].company_name == "Acme Corp"   # filled from the org when profile lacks it
    # No dedup issue if a member also self-listed (login-based dedup).
    assert len([p for p in people if p.full_name == "Ravi Kumar"]) == 1
