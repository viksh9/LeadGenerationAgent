"""Tests for the analysis pipeline and the analyze/leads endpoints."""

from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient
from sqlalchemy.orm import sessionmaker

from api.main import app, get_session
from api.schemas import LeadAnalyzeResponse
from database.models import LeadPriority, SignalType
from database.repository import get_engine, get_lead, init_db
from processors.analysis_pipeline import AnalysisPipeline, run_analysis

pipeline = AnalysisPipeline()

BANKING = (
    "Company won a major banking transformation project and is hiring "
    "30 Java engineers, 10 AWS engineers and 5 DevOps specialists."
)

# A complete HIGH-scoring lead (BFSI industry, recent signal, identifiable POC),
# matching the scoring engine's HOT scenario. Recent date is relative to now so
# the recency category is stable regardless of when the test runs.
RECENT_ISO = (datetime.now(timezone.utc) - timedelta(days=2)).isoformat()
BANKING_LEAD = {
    "company_name": "NorthStar Banking Technologies",
    "industry": "BFSI",
    "signal_description": BANKING,
    "poc_name": "Priya Raman",
    "poc_title": "VP of Engineering",
    "signal_date": RECENT_ISO,
}


# -- pipeline (no persistence) ---------------------------------------------
def test_analyze_builds_full_response():
    resp = pipeline.analyze(BANKING_LEAD)
    assert isinstance(resp, LeadAnalyzeResponse)
    assert resp.score >= 80
    assert resp.priority is LeadPriority.HOT
    assert resp.signals_detected  # detected signals mapped through
    assert resp.opportunity_analysis is not None
    assert resp.poc_recommendation is not None
    assert resp.score_breakdown


def test_analyze_maps_lead_fields():
    resp = pipeline.analyze(BANKING_LEAD)
    lead = resp.lead
    assert lead.company_name == "NorthStar Banking Technologies"
    assert lead.lead_priority is LeadPriority.HOT
    assert lead.estimated_hiring == 45
    assert {"Java", "AWS", "DevOps"}.issubset(set(lead.technologies))
    assert lead.signal_type in set(SignalType)
    assert lead.opportunity_summary
    assert lead.recommended_action
    assert lead.id == 0  # not persisted


def test_weak_signal_low_score():
    resp = pipeline.analyze(
        {"company_name": "Acme", "signal_description": "Hiring one frontend developer."}
    )
    assert resp.score < 40
    assert resp.priority is LeadPriority.LOW


def test_calculated_fields_ignore_client_supplied_values():
    # LeadAnalyzeRequest ignores unknown/calculated fields; the pipeline computes them.
    resp = pipeline.analyze({**BANKING_LEAD, "lead_score": 1})
    assert resp.score >= 80  # computed, not the injected 1


def test_deterministic():
    a = pipeline.analyze({"company_name": "NorthStar", "signal_description": BANKING})
    b = pipeline.analyze({"company_name": "NorthStar", "signal_description": BANKING})
    assert a.model_dump() == b.model_dump()


def test_run_analysis_convenience_wrapper():
    resp = run_analysis({"company_name": "NorthStar", "signal_description": BANKING})
    assert isinstance(resp, LeadAnalyzeResponse)


# -- pipeline (with persistence) -------------------------------------------
def test_analyze_and_store_persists(db_session):
    resp = pipeline.analyze_and_store(db_session, BANKING_LEAD)
    assert resp.lead.id > 0
    stored = get_lead(db_session, resp.lead.id)
    assert stored is not None
    assert stored.company_name == "NorthStar Banking Technologies"
    assert stored.lead_priority is LeadPriority.HOT
    assert stored.lead_score >= 80
    assert stored.recommended_pitch  # pitch persisted


# -- endpoints --------------------------------------------------------------
def _client(tmp_path):
    engine = get_engine(f"sqlite:///{tmp_path / 'api.db'}")
    init_db(engine)
    factory = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)

    def override():
        session = factory()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_session] = override
    return TestClient(app)


def test_health_still_works(tmp_path):
    client = _client(tmp_path)
    try:
        assert client.get("/health").json()["status"] == "ok"
    finally:
        app.dependency_overrides.clear()


def test_analyze_endpoint_persists_and_returns(tmp_path):
    client = _client(tmp_path)
    try:
        resp = client.post("/analyze", json=BANKING_LEAD)
        assert resp.status_code == 200
        body = resp.json()
        assert body["lead"]["id"] > 0
        assert body["priority"] == "HOT"
        assert body["lead"]["signal_type"] in {s.value for s in SignalType}

        listed = client.get("/leads")
        assert listed.status_code == 200
        assert listed.json()["total"] >= 1

        lead_id = body["lead"]["id"]
        detail = client.get(f"/leads/{lead_id}")
        assert detail.status_code == 200
        assert detail.json()["company_name"] == "NorthStar Banking Technologies"

        missing = client.get("/leads/999999")
        assert missing.status_code == 404
        assert missing.json()["error"]["code"] == "not_found"
    finally:
        app.dependency_overrides.clear()


def test_analyze_endpoint_requires_company_name(tmp_path):
    client = _client(tmp_path)
    try:
        resp = client.post("/analyze", json={"signal_description": "hiring engineers"})
        assert resp.status_code == 422
    finally:
        app.dependency_overrides.clear()
