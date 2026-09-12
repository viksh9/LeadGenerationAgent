"""Public-intelligence API tests (Prompt 45) — routing, RBAC, honest states."""

from __future__ import annotations

import api.main
from api.dependencies import get_session
from database.models import (
    Company,
    DataProvenance,
    DecisionMaker,
    Lead,
    LeadPriority,
    LeadStatus,
    SignalType,
    VerificationStatus,
)


def _seed(client, *, with_public_poc=False):
    session = next(api.main.app.dependency_overrides[get_session]())
    session.add(Company(canonical_name="Acme Corp", normalized_name="acme corp",
                        primary_domain="acme.com", data_provenance=DataProvenance.REAL))
    lead = Lead(company_name="Acme Corp", normalized_company_name="acme corp", lead_score=80,
                lead_priority=LeadPriority.HOT, status=LeadStatus.NEW, signal_type=SignalType.HIRING,
                estimated_hiring=30, data_provenance=DataProvenance.REAL)
    session.add(lead)
    session.flush()
    company = session.query(Company).first()
    if with_public_poc:
        session.add(DecisionMaker(
            company_id=company.id, company_name="Acme Corp", full_name="Jane Doe",
            normalized_name="jane doe", job_title="VP Engineering",
            professional_network_url="https://github.com/jane", contact_source="GitHub",
            source_type="github_public_profile", source_url="https://github.com/jane",
            match_score=90, contact_trust_score=55, contact_trust_status="VERIFIED",
            verification_status=VerificationStatus.VERIFIED, is_current=True,
            data_provenance=DataProvenance.REAL))
    lead_id, cid = lead.id, company.id
    session.commit()
    session.close()
    return lead_id, cid


def test_company_public_intelligence_shape(client):
    _lead_id, cid = _seed(client, with_public_poc=True)
    body = client.get(f"/companies/{cid}/public-intelligence").json()
    assert body["company_id"] == cid and body["company_name"] == "Acme Corp"
    assert len(body["public_leadership"]) == 1
    assert body["public_leadership"][0]["full_name"] == "Jane Doe"
    assert body["public_leadership"][0]["contact_source"] == "GitHub"


def test_company_public_intelligence_404(client):
    assert client.get("/companies/999999/public-intelligence").status_code == 404


def test_lead_pocs_includes_public_poc(client):
    lead_id, _cid = _seed(client, with_public_poc=True)
    body = client.get(f"/leads/{lead_id}/pocs").json()
    assert any(p["contact_source"] == "GitHub" for p in body["pocs"])


def test_test_endpoint_disabled_provider(client):
    body = client.post("/public-intelligence/test?provider=public_registry").json()
    assert body["result"] == "NOT_CONFIGURED" and body["performed_request"] is False


def test_discover_rbac_enforced_when_key_set(client, monkeypatch):
    from config import settings as sm
    settings = sm.get_settings()
    monkeypatch.setattr(settings, "admin_api_key", "secret")
    # Disable PI so the authorized 200 path short-circuits (no real network in tests).
    monkeypatch.setattr(settings, "public_intelligence_enabled", False)
    lead_id, _cid = _seed(client)
    assert client.post(f"/leads/{lead_id}/public-intelligence/discover").status_code == 403
    assert client.post("/public-intelligence/test?provider=public_registry").status_code == 403
    ok = client.post(f"/leads/{lead_id}/public-intelligence/discover", headers={"X-Admin-Key": "secret"})
    assert ok.status_code == 200 and ok.json()["status"] == "DISABLED"
