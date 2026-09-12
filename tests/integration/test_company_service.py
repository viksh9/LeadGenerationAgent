"""Integration tests: company resolution/upsert + intelligence + API (§32)."""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import sessionmaker

import api.main
from api.dependencies import get_session
from collectors.raw_record import normalize_company_name
from database.models import (
    Company,
    CompanyResolutionCandidate,
    DataProvenance,
    JobRecord,
    Lead,
    LeadPriority,
)
from database.repository import create_lead, get_engine, init_db
from company.service import CompanyIntelligenceService, CompanyResolutionService

NOW = datetime(2026, 9, 5)


def _job(session, *, company, domain=None, title="Java Developer", techs=("Java",), city="Bengaluru", ext, days_ago=3):
    jr = JobRecord(
        content_hash=ext, canonical_key=f"{normalize_company_name(company)}|{title}|{city}".lower(),
        company_name=company, normalized_company_name=normalize_company_name(company), company_domain=domain,
        original_job_title=title, normalized_title=title, normalized_role=title,
        city=city, technologies=list(techs), published_at=NOW - timedelta(days=days_ago),
        data_provenance=DataProvenance.REAL, primary_source="adzuna", source_count=1, job_category="Software",
    )
    session.add(jr)
    session.flush()
    return jr


def _lead(session, company):
    return create_lead(session, company_name=company, normalized_company_name=normalize_company_name(company),
                       data_provenance=DataProvenance.REAL, it_job_count=5, lead_score=80.0,
                       lead_priority=LeadPriority.HOT, evidence_confidence=70, verification_status="VERIFIED")


def _count(session, model):
    return session.scalar(select(func.count()).select_from(model))


def test_reobserving_same_name_no_domain_links_not_duplicates(seed_session):
    """Prompt 57 regression: the SAME real company re-observed by exact normalized name
    with no domain (typical Adzuna re-ingestion) must LINK to the existing company, never
    create a duplicate identity."""
    from company.resolver import ObservedCompany
    svc = CompanyResolutionService(seed_session)
    obs = lambda: ObservedCompany(name="Zeta Systems", domain=None, city="Pune",
                                  source_id="adzuna", source_url=None)
    c1, _ = svc.resolve_and_upsert(obs(), provenance=DataProvenance.REAL, now=NOW)
    seed_session.commit()
    c2, _ = svc.resolve_and_upsert(obs(), provenance=DataProvenance.REAL, now=NOW)
    seed_session.commit()
    assert c1.id == c2.id                       # linked, same company
    assert _count(seed_session, Company) == 1   # no duplicate created
    dups = seed_session.execute(
        select(Company.normalized_name, func.count(Company.id))
        .group_by(Company.normalized_name).having(func.count(Company.id) > 1)).all()
    assert dups == []


def test_same_domain_different_names_one_company(seed_session):
    _job(seed_session, company="ABC Technologies", domain="abc.com", ext="j1")
    _job(seed_session, company="ABC Technologies Pvt Ltd", domain="abc.com", ext="j2", title="Python Developer", techs=("Python",))
    seed_session.commit()
    summary = CompanyResolutionService(seed_session).upsert_companies_from_jobs(provenance=DataProvenance.REAL, now=NOW)
    # Same normalized name -> one group -> one company (Scenario A).
    assert _count(seed_session, Company) == 1


def test_different_companies_not_merged(seed_session):
    _job(seed_session, company="ABC Technologies", domain="abc.com", ext="j1")
    _job(seed_session, company="XYZ Digital", domain="xyz.com", ext="j2")
    seed_session.commit()
    CompanyResolutionService(seed_session).upsert_companies_from_jobs(provenance=DataProvenance.REAL, now=NOW)
    assert _count(seed_session, Company) == 2   # Scenario B — no false merge


def test_domain_link_across_different_normalized_names(seed_session):
    _job(seed_session, company="ABC Technologies", domain="abc.com", ext="j1")
    _job(seed_session, company="ABC Corp", domain="abc.com", ext="j2", title="Cloud Engineer", techs=("AWS",))
    seed_session.commit()
    CompanyResolutionService(seed_session).upsert_companies_from_jobs(provenance=DataProvenance.REAL, now=NOW)
    # Different names but same verified domain -> resolver links them (1 company).
    assert _count(seed_session, Company) == 1


def test_company_intelligence_aggregation(seed_session):
    for i in range(20):
        tech = [("Java",), ("AWS",), ("DevOps",)][i % 3]
        _job(seed_session, company="Ravi Technologies", domain="ravi.com", ext=f"j{i}", techs=tech,
             title=["Java Developer", "AWS Engineer", "DevOps Engineer"][i % 3])
    _lead(seed_session, "Ravi Technologies")
    seed_session.commit()
    CompanyResolutionService(seed_session).upsert_companies_from_jobs(provenance=DataProvenance.REAL, now=NOW)
    company = seed_session.scalars(select(Company)).first()
    profile = CompanyIntelligenceService(seed_session).profile(company.id, now=NOW)
    assert profile["hiring"]["canonical_active_openings"] == 20   # canonical jobs, not source rows
    techs = {t["technology"] for t in profile["technology_demand"]}
    assert {"Java", "AWS", "DevOps"} <= techs
    assert profile["geography"]["india_locations"] == ["Bengaluru"]
    # A linked lead's verification propagates to the company.
    lead = seed_session.scalars(select(Lead)).first()
    assert lead.company_id == company.id


def test_idempotent_reruns(seed_session):
    _job(seed_session, company="Ravi Technologies", domain="ravi.com", ext="j1")
    seed_session.commit()
    svc = CompanyResolutionService(seed_session)
    svc.upsert_companies_from_jobs(provenance=DataProvenance.REAL, now=NOW)
    svc.upsert_companies_from_jobs(provenance=DataProvenance.REAL, now=NOW)
    assert _count(seed_session, Company) == 1   # no duplicate company on re-run


def test_review_queue_for_same_name_different_domain(seed_session):
    # Pre-existing company, then a job with same name but a conflicting domain.
    c = Company(canonical_name="ABC Technologies", normalized_name="abc technologies",
                primary_domain="abc.com", data_provenance=DataProvenance.REAL)
    seed_session.add(c)
    seed_session.flush()
    _job(seed_session, company="ABC Technologies", domain="abc-different.in", ext="j1")
    seed_session.commit()
    summary = CompanyResolutionService(seed_session).upsert_companies_from_jobs(provenance=DataProvenance.REAL, now=NOW)
    assert summary.review_candidates >= 1
    assert _count(seed_session, CompanyResolutionCandidate) >= 1


# --- API -------------------------------------------------------------------- #
@pytest.fixture
def company_client(tmp_path):
    engine = get_engine(f"sqlite:///{tmp_path / 'co.db'}")
    init_db(engine)
    factory = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)
    with factory() as s:
        for i in range(6):
            _job(s, company="Ravi Technologies", domain="ravi.com", ext=f"j{i}",
                 title=["Java Developer", "AWS Engineer"][i % 2], techs=[("Java",), ("AWS",)][i % 2])
        _lead(s, "Ravi Technologies")
        s.commit()
        CompanyResolutionService(s).upsert_companies_from_jobs(provenance=DataProvenance.REAL, now=NOW)
        cid = s.scalars(select(Company.id)).first()

    def override():
        session = factory()
        try:
            yield session
        finally:
            session.close()

    api.main.app.dependency_overrides[get_session] = override
    yield TestClient(api.main.app), cid
    api.main.app.dependency_overrides.clear()


def test_companies_list_and_search(company_client):
    client, _ = company_client
    r = client.get("/companies", params={"search": "Ravi"}).json()
    assert r["total"] >= 1 and r["items"][0]["canonical_name"].startswith("Ravi")


def test_company_intelligence_endpoint(company_client):
    client, cid = company_client
    intel = client.get(f"/companies/{cid}/intelligence").json()
    assert intel["hiring"]["canonical_active_openings"] == 6
    assert intel["technology_demand"]
    assert intel["evidence"]["verification_status"] in {"VERIFIED", "PARTIALLY_VERIFIED", "UNVERIFIED", "STALE", "CONTRADICTED"}


def test_company_history_endpoint(company_client):
    client, cid = company_client
    hist = client.get(f"/companies/{cid}/history").json()
    assert hist["events"]
