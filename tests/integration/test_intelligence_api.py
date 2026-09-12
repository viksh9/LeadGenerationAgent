"""Lead Intelligence API endpoints (Prompt 50, §43/§46). Throwaway DB via `client`."""

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
    PersonMatchStatus,
    SignalType,
    VerificationStatus,
    utcnow,
)


def _seed(client, *, with_poc=True):
    session = next(api.main.app.dependency_overrides[get_session]())
    session.add(Company(canonical_name="Acme Tech", normalized_name="acme tech", primary_domain="acme.com",
                        industry="IT Services", india_presence=True, full_address="Bengaluru, Karnataka",
                        data_trust_score=82, data_provenance=DataProvenance.REAL))
    lead = Lead(company_name="Acme Tech", normalized_company_name="acme tech", lead_score=85,
                lead_priority=LeadPriority.HOT, status=LeadStatus.NEW, signal_type=SignalType.HIRING,
                estimated_hiring=47, it_job_count=47, technologies=["Java", "AWS"],
                source_name="Official Career Site", source_url="https://acme.com/careers",
                data_provenance=DataProvenance.REAL)
    session.add(lead)
    session.flush()
    company = session.query(Company).first()
    if with_poc:
        session.add(DecisionMaker(
            company_id=company.id, company_name="Acme Tech", full_name="Jane Doe", normalized_name="jane doe",
            normalized_role="vp engineering", job_title="VP Engineering", role_match_score=92,
            contact_trust_score=70, contact_trust_status="LIKELY", employment_status="CURRENT_LIKELY",
            is_current=True, business_email="jane@acme.com", email_verification_status="VALID",
            contact_type=ContactType.BUSINESS_EMAIL, email_status=EmailStatus.UNVERIFIED_SOURCE,
            verification_status=VerificationStatus.PARTIALLY_VERIFIED, match_status=PersonMatchStatus.POSSIBLE_MATCH,
            contact_source="Apollo", source_type="contact_enrichment", freshness_score=95,
            last_verified_at=utcnow(), last_seen_at=utcnow(), data_provenance=DataProvenance.REAL))
    lead_id = lead.id
    session.commit()
    session.close()
    return lead_id


def test_get_intelligence_shape(client):
    lead_id = _seed(client)
    body = client.get(f"/leads/{lead_id}/intelligence").json()
    assert body["data_trust"] == 82 and body["contact_trust"] == 70
    assert body["lead_score"] == 85
    assert body["primary_poc"]["poc"]["full_name"] == "Jane Doe"
    assert body["primary_poc"]["poc_status"] == "LIKELY"
    assert body["primary_poc"]["role_match_score"] == 92
    assert "47" in body["signal_summary"]
    assert body["ai_highlights"]["ai_available"] is False          # no provider configured
    assert body["ai_highlights"]["ai_insight"] is None
    titles = [h["highlight_title"] for h in body["ai_highlights"]["highlights"]]
    assert "Hiring Trend" in titles
    labels = {s["source"] for s in body["sources"]}
    assert "Apollo" in labels and "Hunter" not in labels           # only contributing sources


def test_recommended_role_only_when_no_person(client):
    lead_id = _seed(client, with_poc=False)
    body = client.get(f"/leads/{lead_id}/intelligence").json()
    assert body["primary_poc"] is None
    assert body["contact_trust"] == 0
    assert body["recommended_roles"]                                # roles, never a fake person


def test_get_sources(client):
    lead_id = _seed(client)
    body = client.get(f"/leads/{lead_id}/sources").json()
    assert body["lead_id"] == lead_id
    assert any(s["source"] == "Apollo" for s in body["sources"])


def test_intelligence_404(client):
    assert client.get("/leads/999999/intelligence").status_code == 404
    assert client.get("/leads/999999/sources").status_code == 404


def test_refresh_rbac_and_rate_open_in_dev(client):
    lead_id = _seed(client)
    # Dev mode (no admin key) -> refresh allowed.
    r = client.post(f"/leads/{lead_id}/intelligence/refresh")
    assert r.status_code == 200 and r.json()["lead_id"] == lead_id


def test_refresh_rbac_enforced_when_key_set(client, monkeypatch):
    from config import settings as sm
    monkeypatch.setattr(sm.get_settings(), "admin_api_key", "secret")
    lead_id = _seed(client)
    assert client.post(f"/leads/{lead_id}/intelligence/refresh").status_code == 403
    ok = client.post(f"/leads/{lead_id}/intelligence/refresh", headers={"X-Admin-Key": "secret"})
    assert ok.status_code == 200
    assert client.get(f"/leads/{lead_id}/intelligence").status_code == 200   # GET stays open
