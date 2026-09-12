"""POC / ContactOut API endpoint tests (Prompt 44).

Throwaway DB via the `client` fixture. Verifies routing, schemas, RBAC on
credit-spending endpoints, honest NOT_CONFIGURED states, role-only recommendations,
real-person read path, and that the API token is never exposed.
"""

from __future__ import annotations

import api.main
from api.dependencies import get_session
from database.models import (
    Company,
    ContactType,
    DataProvenance,
    DecisionMaker,
    EmailStatus,
    Lead,
    LeadPriority,
    LeadStatus,
    SignalType,
    VerificationStatus,
)


def _seed(client, *, with_poc=False):
    session = next(api.main.app.dependency_overrides[get_session]())
    session.add(Company(canonical_name="Acme Corp", normalized_name="acme corp",
                        primary_domain="acme.com", data_provenance=DataProvenance.REAL))
    lead = Lead(company_name="Acme Corp", normalized_company_name="acme corp", lead_score=80,
                lead_priority=LeadPriority.HOT, status=LeadStatus.NEW, signal_type=SignalType.HIRING,
                estimated_hiring=30, data_provenance=DataProvenance.REAL)
    session.add(lead)
    session.flush()
    company = session.query(Company).first()
    if with_poc:
        session.add(DecisionMaker(
            company_id=company.id, company_name="Acme Corp", full_name="Jane Doe",
            normalized_name="jane doe", job_title="VP Engineering", business_email="jane@acme.com",
            business_phone="+91-80-1234", professional_network_url="https://linkedin.com/in/janedoe",
            contact_type=ContactType.BUSINESS_EMAIL, email_status=EmailStatus.VERIFIED_SOURCE,
            verification_status=VerificationStatus.VERIFIED, contact_source="ContactOut",
            source_type="contact_enrichment", source_record_id="janedoe", match_score=98,
            contact_trust_score=100, contact_trust_status="VERIFIED", is_current=True,
            data_provenance=DataProvenance.REAL))
    lead_id = lead.id
    session.commit()
    session.close()
    return lead_id


def test_status_endpoint_not_configured_and_no_token(client):
    body = client.get("/integrations/contactout/status").json()
    assert body["status"] == "NOT_CONFIGURED" and body["configured"] is False
    assert "token" not in body and "api_token" not in body        # never exposed
    assert body["max_poc_searches_per_opportunity"] >= 1


def test_test_connection_not_configured(client):
    body = client.post("/integrations/contactout/test").json()
    assert body["connection_status"] == "NOT_CONFIGURED" and body["performed_request"] is False


def test_lead_pocs_returns_role_recommendations(client):
    lead_id = _seed(client)
    body = client.get(f"/leads/{lead_id}/pocs").json()
    assert body["contactout_status"] == "NOT_CONFIGURED"
    assert body["note"] == "POC enrichment is not configured."
    assert len(body["recommended_roles"]) > 0            # role-only recommendations shown
    assert body["pocs"] == []                            # no fabricated people


def test_lead_pocs_returns_real_person(client):
    lead_id = _seed(client, with_poc=True)
    body = client.get(f"/leads/{lead_id}/pocs").json()
    assert len(body["pocs"]) == 1
    poc = body["pocs"][0]
    assert poc["full_name"] == "Jane Doe" and poc["business_email"] == "jane@acme.com"
    assert poc["contact_trust_status"] == "VERIFIED" and poc["match_score"] == 98
    assert poc["contact_source"] == "ContactOut"


def test_discover_not_configured(client):
    lead_id = _seed(client)
    body = client.post(f"/leads/{lead_id}/pocs/discover").json()
    assert body["status"] == "NOT_CONFIGURED" and body["pocs"] == []


def test_lead_pocs_404(client):
    assert client.get("/leads/999999/pocs").status_code == 404
    assert client.get("/pocs/999999").status_code == 404


def test_rbac_enforced_when_key_set(client, monkeypatch):
    from config import settings as sm
    monkeypatch.setattr(sm.get_settings(), "admin_api_key", "secret")
    lead_id = _seed(client)
    # No role → discover/enrich/test are forbidden (credit-spending / outbound).
    assert client.post(f"/leads/{lead_id}/pocs/discover").status_code == 403
    assert client.post("/integrations/contactout/test").status_code == 403
    # With admin key → allowed (still NOT_CONFIGURED, but authorized).
    ok = client.post(f"/leads/{lead_id}/pocs/discover", headers={"X-Admin-Key": "secret"})
    assert ok.status_code == 200
    # Read status remains open.
    assert client.get("/integrations/contactout/status").status_code == 200
