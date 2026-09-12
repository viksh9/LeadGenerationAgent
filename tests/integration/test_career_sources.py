"""Tests for company→ATS discovery, the career-source registry, and the APIs.

All offline: discovery uses a mocked SafeHttpClient (httpx.MockTransport); the API
discovery/check/collect endpoints are exercised with monkeypatched services so no
real network call is made.
"""

from __future__ import annotations

import httpx
import pytest

from collectors.career_source_registry import (
    list_for_company,
    register_from_discovery,
)
from collectors.company.career_source_discovery import (
    DiscoveryResult,
    detect_ats,
    discover_career_source,
)
from collectors.company.config import load_career_config
from collectors.company.http_client import SafeHttpClient
from database.models import AtsProvider, CareerSourceStatus


# --------------------------------------------------------------------------- #
# Detection
# --------------------------------------------------------------------------- #
def test_detect_greenhouse_from_link():
    provider, board = detect_ats('<a href="https://boards.greenhouse.io/acmecorp">Jobs</a>',
                                 "https://acme.com/careers")
    assert provider is AtsProvider.GREENHOUSE and board == "acmecorp"


def test_detect_lever_from_redirect():
    provider, board = detect_ats("<html></html>", "https://jobs.lever.co/acmeco")
    assert provider is AtsProvider.LEVER and board == "acmeco"


def test_detect_none_when_no_ats():
    assert detect_ats("<p>careers</p>", "https://acme.com/careers") == (None, None)


def test_detect_ignores_stopword_paths():
    # embed helper path must not be captured as a board id
    provider, board = detect_ats("boards.greenhouse.io/embed/job_board?for=realco", "https://x")
    assert provider is AtsProvider.GREENHOUSE and board == "realco"


# --------------------------------------------------------------------------- #
# Discovery service (mocked safe client)
# --------------------------------------------------------------------------- #
def _client(handler):
    return SafeHttpClient(load_career_config(), http=httpx.Client(transport=httpx.MockTransport(handler)))


def test_discover_finds_and_verifies_greenhouse():
    client = _client(lambda r: httpx.Response(
        200, text='<a href="https://boards.greenhouse.io/acmecorp">Open roles</a>',
        headers={"content-type": "text/html"}))
    result = discover_career_source(company_id=1, company_name="Acme", domain="acme.com", client=client)
    assert result.verified is True
    assert result.provider is AtsProvider.GREENHOUSE
    assert result.board_identifier == "acmecorp"
    assert result.discovery_method == "careers_page_link"


def test_discover_returns_unverified_when_nothing_found():
    client = _client(lambda r: httpx.Response(200, text="<p>no ats</p>",
                                              headers={"content-type": "text/html"}))
    result = discover_career_source(company_id=1, company_name="Acme", domain="acme.com", client=client)
    assert result.verified is False and result.provider is None


def test_discover_no_domain_no_probe():
    result = discover_career_source(company_id=1, company_name="Acme")
    assert result.verified is False
    assert "No company domain" in result.detail


# --------------------------------------------------------------------------- #
# Registry
# --------------------------------------------------------------------------- #
def test_register_from_discovery_idempotent(seed_session):
    result = DiscoveryResult(company_id=7, company_name="Acme", provider=AtsProvider.GREENHOUSE,
                             board_identifier="acmecorp", careers_url="https://acme.com/careers",
                             verified=True, discovery_method="careers_page_link")
    row1 = register_from_discovery(seed_session, result)
    row2 = register_from_discovery(seed_session, result)      # same board → upsert, not duplicate
    assert row1 is not None and row1.id == row2.id
    assert row1.status is CareerSourceStatus.CONFIGURED
    assert row1.company_id == 7
    assert len(list_for_company(seed_session, 7)) == 1


def test_register_from_discovery_skips_unverified(seed_session):
    assert register_from_discovery(seed_session, DiscoveryResult(company_id=1, company_name="X")) is None


# --------------------------------------------------------------------------- #
# API
# --------------------------------------------------------------------------- #
def test_career_sources_api_list_get_404(client, seed_session):
    assert client.get("/career-sources").json() == {"items": [], "total": 0}
    assert client.get("/career-sources/123").status_code == 404


def test_discover_endpoint_registers(client, monkeypatch):
    from types import SimpleNamespace

    fake_company = SimpleNamespace(id=42, canonical_name="Acme", primary_domain="acme.com",
                                   website="https://acme.com")
    monkeypatch.setattr("api.routes.career_sources.company_repo.get_company",
                        lambda session, cid: fake_company if cid == 42 else None)

    def fake_discover(**kwargs):
        return DiscoveryResult(company_id=kwargs.get("company_id"), company_name=kwargs.get("company_name"),
                               provider=AtsProvider.LEVER, board_identifier="acmeco",
                               careers_url="https://acme.com/careers", verified=True,
                               discovery_method="careers_page_link", detail="found")
    monkeypatch.setattr("api.routes.career_sources.discover_career_source", fake_discover)

    body = client.post("/companies/42/discover-career-source").json()
    assert body["found"] is True and body["verified"] is True
    assert body["provider"] == "LEVER" and body["board_identifier"] == "acmeco"
    assert body["career_source"]["status"] == "CONFIGURED"
    assert client.get("/companies/42/career-sources").json()["total"] == 1


def test_discover_endpoint_unknown_company_404(client):
    assert client.post("/companies/999999/discover-career-source").status_code == 404


# --------------------------------------------------------------------------- #
# Ad-hoc discovery from a provided domain / careers URL (no Company entity)
# --------------------------------------------------------------------------- #
def test_adhoc_discover_requires_domain_or_url(client):
    # Company name alone is not enough — there's nothing real to probe.
    r = client.post("/career-sources/discover", json={"company_name": "Acme"})
    assert r.status_code == 422
    assert "domain or careers URL" in r.json()["error"]["message"]


def test_adhoc_discover_requires_company_name(client):
    r = client.post("/career-sources/discover", json={"company_name": "", "domain": "acme.com"})
    assert r.status_code == 422   # schema min_length


def test_adhoc_discover_found(client, monkeypatch):
    captured = {}

    def fake_discover(**kwargs):
        captured.update(kwargs)
        return DiscoveryResult(company_id=kwargs.get("company_id"), company_name=kwargs.get("company_name"),
                               provider=AtsProvider.GREENHOUSE, board_identifier="acmecorp",
                               careers_url="https://acme.com/careers", verified=True,
                               discovery_method="careers_page_link", detail="Found Greenhouse board 'acmecorp'.")
    monkeypatch.setattr("api.routes.career_sources.discover_career_source", fake_discover)

    body = client.post("/career-sources/discover",
                       json={"company_name": "Acme", "domain": "acme.com"}).json()
    assert body["found"] is True and body["verified"] is True
    assert body["provider"] == "GREENHOUSE" and body["board_identifier"] == "acmecorp"
    assert body["company_id"] is None and body["career_source"] is None   # nothing persisted
    assert captured["company_id"] is None and captured["domain"] == "acme.com"


def test_adhoc_discover_not_found_is_honest(client, monkeypatch):
    monkeypatch.setattr(
        "api.routes.career_sources.discover_career_source",
        lambda **k: DiscoveryResult(company_id=None, company_name=k.get("company_name"),
                                    verified=False, detail="No supported ATS detected on the page."),
    )
    body = client.post("/career-sources/discover",
                       json={"company_name": "Acme", "careers_url": "https://acme.com/careers"}).json()
    assert body["found"] is False and body["verified"] is False
    assert body["provider"] is None and body["board_identifier"] is None
