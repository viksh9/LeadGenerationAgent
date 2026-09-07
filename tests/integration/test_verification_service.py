"""Integration tests: EvidenceVerificationService + verification API."""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import sessionmaker

import api.main
from api.dependencies import get_session
from database.models import DataProvenance, EvidenceRecord, LeadPriority, VerificationStatus
from database.repository import create_lead, get_engine, init_db
from verification.service import EvidenceVerificationService

NOW = datetime(2026, 9, 5)


def _lead(session, *, company="Ravi Technologies", provenance=DataProvenance.REAL, evidence=None, score=90.0):
    return create_lead(
        session, company_name=company, normalized_company_name=company.lower(),
        data_provenance=provenance, it_job_count=20, lead_score=score, lead_priority=LeadPriority.HOT,
        company_signals=["LARGE_TECH_HIRING"], technologies=["Java"],
        evidence=evidence if evidence is not None else [
            {"source": "company_career", "source_id": "company_career", "source_url": "https://c/1",
             "job_title": "Senior Java Developer", "published_at": (NOW - timedelta(days=3)).isoformat()},
        ],
    )


def test_verify_lead_sets_four_distinct_scores(seed_session):
    lead = _lead(seed_session)
    EvidenceVerificationService(seed_session).verify_lead(lead, now=NOW)
    seed_session.refresh(lead)
    assert lead.verification_status is VerificationStatus.VERIFIED
    assert lead.source_reliability >= 90
    assert lead.freshness_score >= 80
    # Commercial score is untouched and independent of evidence confidence.
    assert lead.lead_score == 90.0
    assert lead.evidence_confidence != lead.lead_score


def test_verify_lead_persists_evidence_and_is_idempotent(seed_session):
    lead = _lead(seed_session)
    svc = EvidenceVerificationService(seed_session)
    svc.verify_lead(lead, now=NOW)
    first = seed_session.scalar(select(func.count()).select_from(EvidenceRecord))
    svc.verify_lead(lead, now=NOW)   # re-verify
    second = seed_session.scalar(select(func.count()).select_from(EvidenceRecord))
    assert first == second and first >= 1   # no duplicate evidence records


def test_syndicated_urls_not_counted_as_independent(seed_session):
    lead = _lead(seed_session, evidence=[
        {"source_id": "company_career", "source_url": "https://a/1", "job_title": "Senior Java Developer",
         "published_at": (NOW - timedelta(days=3)).isoformat()},
        {"source_id": "adzuna", "source_url": "https://b/1", "job_title": "Senior Java Developer",
         "published_at": (NOW - timedelta(days=3)).isoformat()},
        {"source_id": "rss_news", "source_url": "https://c/1", "job_title": "Senior Java Developer",
         "published_at": (NOW - timedelta(days=3)).isoformat()},
    ])
    EvidenceVerificationService(seed_session).verify_lead(lead, now=NOW)
    seed_session.refresh(lead)
    assert lead.independent_support_count == 1   # one underlying job across three URLs


def test_stale_lead_readiness_hold(seed_session):
    lead = _lead(seed_session, evidence=[
        {"source_id": "company_career", "source_url": "https://a/1", "job_title": "Senior Java Developer",
         "published_at": (NOW - timedelta(days=300)).isoformat()},
    ])
    EvidenceVerificationService(seed_session).verify_lead(lead, now=NOW)
    seed_session.refresh(lead)
    assert lead.verification_status is VerificationStatus.STALE
    assert lead.lead_readiness.value == "HOLD"


# --- API -------------------------------------------------------------------- #
@pytest.fixture
def client_with_lead(tmp_path):
    engine = get_engine(f"sqlite:///{tmp_path / 'verify.db'}")
    init_db(engine)
    factory = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)
    with factory() as s:
        lead = _lead(s)
        EvidenceVerificationService(s).verify_lead(lead, now=NOW)
        lead_id = lead.id

    def override():
        session = factory()
        try:
            yield session
        finally:
            session.close()

    api.main.app.dependency_overrides[get_session] = override
    yield TestClient(api.main.app), lead_id
    api.main.app.dependency_overrides.clear()


def test_verification_endpoint(client_with_lead):
    client, lead_id = client_with_lead
    v = client.get(f"/leads/{lead_id}/verification").json()
    assert v["verification_status"] == "VERIFIED"
    # Four distinct numbers are all exposed separately.
    for key in ("lead_score", "source_reliability", "evidence_confidence", "freshness_score"):
        assert key in v
    assert len(v["supporting_sources"]) >= 1


def test_evidence_endpoint(client_with_lead):
    client, lead_id = client_with_lead
    ev = client.get(f"/leads/{lead_id}/evidence").json()
    assert isinstance(ev, list) and ev
    assert ev[0]["source_tier"].startswith("TIER_")


def test_reverify_endpoint(client_with_lead):
    client, lead_id = client_with_lead
    r = client.post(f"/leads/{lead_id}/verify")
    assert r.status_code == 200 and r.json()["verification_status"] in {
        "VERIFIED", "PARTIALLY_VERIFIED", "UNVERIFIED", "STALE", "CONTRADICTED"}
