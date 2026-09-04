"""Tests for the (legacy) processors AnalysisPipeline. API endpoint tests live
in tests/integration/test_lead_api.py."""

from datetime import datetime, timedelta, timezone

from api.schemas import LeadAnalyzeResponse
from database.models import LeadPriority, SignalType
from database.repository import get_lead
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
