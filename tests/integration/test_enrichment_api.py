"""Enrichment provider API endpoints (Prompt 49, §45/§46).

Throwaway DB via the `client` fixture. Verifies the admin status endpoint (config +
capabilities, never a key), per-provider connectivity test honest states (no key ⇒
NOT_CONFIGURED and no outbound request), unknown-provider validation, and RBAC on the
credit-spending test/enrich endpoints.
"""

from __future__ import annotations

import pytest

import api.main
from api.dependencies import get_session
from config import get_settings
from database.models import (
    Company,
    DataProvenance,
    Lead,
    LeadPriority,
    LeadStatus,
    SignalType,
)


@pytest.fixture(autouse=True)
def _no_enrichment_providers(monkeypatch):
    """These tests assert the honest NOT_CONFIGURED state, so ensure no paid provider is
    configured regardless of the ambient .env (a real key in .env must not flip them)."""
    s = get_settings()
    for attr in ("apollo_api_key", "lusha_api_key", "hunter_api_key", "prospeo_api_key",
                 "contactout_api_token"):
        monkeypatch.setattr(s, attr, None, raising=False)
    yield


def test_status_lists_all_providers_with_capabilities_no_keys(client):
    body = client.get("/integrations/enrichment/status").json()
    names = {p["provider"] for p in body["providers"]}
    assert {"contactout", "apollo", "lusha", "prospeo", "hunter"} <= names
    for p in body["providers"]:
        assert p["status"] in ("CONFIGURED", "NOT_CONFIGURED", "DISABLED")
        assert isinstance(p["capabilities"], dict)
        assert "key" not in p and "api_key" not in p        # never exposed


def test_provider_test_not_configured_makes_no_request(client):
    for provider in ("apollo", "lusha", "hunter", "prospeo"):
        body = client.post(f"/integrations/{provider}/test").json()
        assert body["result"] == "NOT_CONFIGURED"
        assert body["performed_request"] is False           # never claims LIVE_VERIFIED without a call


def test_unknown_provider_rejected(client):
    assert client.post("/integrations/bogus/test").status_code == 422


def test_test_endpoint_rbac_enforced_when_key_set(client, monkeypatch):
    from config import settings as sm
    monkeypatch.setattr(sm.get_settings(), "admin_api_key", "secret")
    # No role → credit-spending test endpoint forbidden.
    assert client.post("/integrations/apollo/test").status_code == 403
    # With admin key → authorized (still NOT_CONFIGURED, but allowed).
    ok = client.post("/integrations/apollo/test", headers={"X-Admin-Key": "secret"})
    assert ok.status_code == 200 and ok.json()["result"] == "NOT_CONFIGURED"
    # Read status remains open without a role.
    assert client.get("/integrations/enrichment/status").status_code == 200


def test_enrich_endpoint_not_configured_when_no_providers(client):
    session = next(api.main.app.dependency_overrides[get_session]())
    session.add(Company(canonical_name="Acme Corp", normalized_name="acme corp",
                        primary_domain="acme.com", data_provenance=DataProvenance.REAL))
    lead = Lead(company_name="Acme Corp", normalized_company_name="acme corp", lead_score=80,
                lead_priority=LeadPriority.HOT, status=LeadStatus.NEW, signal_type=SignalType.HIRING,
                estimated_hiring=30, data_provenance=DataProvenance.REAL)
    session.add(lead)
    session.commit()
    lead_id = lead.id
    session.close()
    body = client.post(f"/leads/{lead_id}/contacts/enrich").json()
    assert body["status"] == "NOT_CONFIGURED" and body["persisted"] == 0
    assert body["pocs"] == []                               # no fabricated POC


def test_enrich_endpoint_404_for_missing_lead(client):
    assert client.post("/leads/999999/contacts/enrich").status_code == 404
