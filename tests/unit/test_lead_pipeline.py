"""Unit tests for the LeadAnalysisPipeline orchestrator."""

from datetime import datetime, timedelta, timezone

import pytest

from database.models import LeadPriority, LeadStatus, SignalType
from database.repository import get_lead
from intelligence.lead_pipeline import (
    LeadAnalysisPipeline,
    LeadAnalysisResult,
    LeadPipelineError,
    NormalizedLead,
    normalize_lead,
)

pipeline = LeadAnalysisPipeline()

RECENT = datetime.now(timezone.utc) - timedelta(days=2)

HIGH_LEAD = {
    "company_name": "NorthStar Banking Technologies",
    "industry": "BFSI",
    "signal_title": "Digital Banking Transformation",
    "signal_description": (
        "The company recently won a major banking modernization project and is hiring "
        "30 Java engineers, 10 AWS engineers and 5 DevOps specialists."
    ),
    "technologies": ["Java", "Spring Boot", "AWS", "DevOps"],
    "estimated_hiring": 45,
    "signal_date": RECENT,
    "poc_name": "Priya Raman",
    "poc_title": "VP of Engineering",
    "source_url": "https://news.example/northstar",
}

LOW_LEAD = {
    "company_name": "SmallOffice Solutions",
    "signal_description": "Company posted one office administrator vacancy.",
}


# 1 normalization -----------------------------------------------------------
def test_input_normalization():
    raw = {
        "company_name": "  Acme  ",
        "industry": "  BFSI  ",
        "technologies": ["Java", "java", " AWS ", "AWS", ""],
        "hiring_roles": [" Java Engineer ", "Java Engineer"],
        "signal_title": "   ",
    }
    n = normalize_lead(raw)
    assert isinstance(n, NormalizedLead)
    assert n.company_name == "Acme"
    assert n.industry == "BFSI"
    assert n.technologies == ["Java", "AWS"]  # trimmed + de-duplicated
    assert n.hiring_roles == ["Java Engineer"]
    assert n.signal_title is None  # whitespace normalized to None
    # original payload not mutated
    assert raw["company_name"] == "  Acme  "


def test_normalization_requires_company_name():
    with pytest.raises(LeadPipelineError):
        normalize_lead({"industry": "BFSI"})


# 2 stage ordering / result construction ------------------------------------
def test_pipeline_produces_full_result():
    result = pipeline.analyze(HIGH_LEAD, persist=False)
    assert isinstance(result, LeadAnalysisResult)
    assert result.signal_analysis is not None
    assert result.opportunity_analysis is not None
    assert result.scoring_result is not None
    assert result.poc_recommendation is not None
    assert result.pitch_result is not None
    assert result.final_score == result.scoring_result.score
    assert result.priority == result.scoring_result.priority


# 3-7 engine integration ----------------------------------------------------
def test_signal_detector_integration():
    result = pipeline.analyze(HIGH_LEAD, persist=False)
    assert {SignalType.PROJECT_AWARD, SignalType.HIRING, SignalType.DIGITAL_TRANSFORMATION}.issubset(
        set(result.signal_analysis.signal_types)
    )
    assert result.signal_analysis.estimated_hiring == 45


def test_opportunity_analyzer_integration():
    result = pipeline.analyze(HIGH_LEAD, persist=False)
    assert result.opportunity_analysis.opportunity_type is not None
    assert result.opportunity_analysis.potential_staffing_need.value == "HIGH"


def test_scoring_integration():
    result = pipeline.analyze(HIGH_LEAD, persist=False)
    assert result.priority is LeadPriority.HOT
    assert result.final_score >= 80


def test_poc_integration():
    result = pipeline.analyze(HIGH_LEAD, persist=False)
    assert result.poc_recommendation.primary_role is not None
    assert result.poc_recommendation.primary_role.role in {"VP Engineering", "CTO"}


def test_pitch_integration():
    result = pipeline.analyze(HIGH_LEAD, persist=False)
    assert result.pitch_result.email_subject
    assert result.pitch_result.recommended_pitch


# 8 final result construction (frontend-friendly / serializable) ------------
def test_final_result_serializable():
    result = pipeline.analyze(HIGH_LEAD, persist=False)
    payload = result.model_dump(mode="json")
    assert payload["company_name"] == "NorthStar Banking Technologies"
    assert payload["scoring_result"]["priority"] == "HOT"
    assert payload["poc_recommendation"]["primary_role"]["role"]
    assert isinstance(payload["signal_analysis"]["signal_types"], list)


# 9 persistence -------------------------------------------------------------
def test_database_persistence(db_session):
    result = pipeline.analyze(HIGH_LEAD, session=db_session, persist=True)
    assert result.lead_id and result.lead_id > 0
    stored = get_lead(db_session, result.lead_id)
    assert stored is not None
    assert stored.company_name == "NorthStar Banking Technologies"
    assert stored.lead_priority is LeadPriority.HOT
    assert stored.status is LeadStatus.NEW
    assert stored.recommended_pitch


# 10 duplicate handling -----------------------------------------------------
def test_duplicate_handling_updates_not_duplicates(db_session):
    first = pipeline.analyze(HIGH_LEAD, session=db_session, persist=True)
    second = pipeline.analyze(HIGH_LEAD, session=db_session, persist=True)
    assert first.already_existed is False
    assert second.already_existed is True
    assert first.lead_id == second.lead_id  # same row updated, not duplicated


# 11 reanalysis -------------------------------------------------------------
def test_reanalysis_refreshes_and_sets_last_verified(db_session):
    created = pipeline.analyze(HIGH_LEAD, session=db_session, persist=True)
    before = get_lead(db_session, created.lead_id)
    before.status = LeadStatus.CONTACTED  # simulate lifecycle progress
    db_session.commit()

    result = pipeline.reanalyze(db_session, created.lead_id)
    refreshed = get_lead(db_session, created.lead_id)
    assert result.lead_id == created.lead_id
    assert refreshed.last_verified_at is not None
    assert refreshed.status is LeadStatus.CONTACTED  # lifecycle preserved


# 12 error handling ---------------------------------------------------------
def test_error_handling_wraps_stage_failure():
    class BoomDetector:
        def detect(self, _inp):
            raise RuntimeError("internal detail that must not leak")

    broken = LeadAnalysisPipeline(detector=BoomDetector())
    with pytest.raises(LeadPipelineError) as exc:
        broken.analyze(HIGH_LEAD, persist=False)
    assert exc.value.stage == "signal detection"
    assert "signal detection" in str(exc.value)
    assert "internal detail" not in str(exc.value)


def test_reanalyze_missing_lead(db_session):
    from config.exceptions import NotFoundError

    with pytest.raises(NotFoundError):
        pipeline.reanalyze(db_session, 999999)


# 13 missing optional fields ------------------------------------------------
def test_missing_optional_fields():
    result = pipeline.analyze({"company_name": "Acme", "signal_description": "Hiring engineers."}, persist=False)
    assert isinstance(result, LeadAnalysisResult)
    assert result.company_name == "Acme"


# 14 low-quality lead -------------------------------------------------------
def test_low_quality_lead_is_not_a_strong_opportunity():
    result = pipeline.analyze(LOW_LEAD, persist=False)
    assert result.priority in {LeadPriority.LOW, LeadPriority.NURTURE}
    assert result.final_score < 40


# 15 high-quality lead ------------------------------------------------------
def test_high_quality_lead():
    result = pipeline.analyze(HIGH_LEAD, persist=False)
    assert result.priority is LeadPriority.HOT
    assert {"Java", "AWS", "DevOps"}.issubset(set(result.signal_analysis.detected_technologies))


# 21 determinism ------------------------------------------------------------
def test_determinism_of_intelligence_outputs():
    a = pipeline.analyze(HIGH_LEAD, persist=False)
    b = pipeline.analyze(HIGH_LEAD, persist=False)
    assert a.signal_analysis.model_dump() == b.signal_analysis.model_dump()
    assert a.opportunity_analysis.opportunity_type == b.opportunity_analysis.opportunity_type
    assert a.final_score == b.final_score
    assert a.priority == b.priority
    assert a.poc_recommendation.model_dump() == b.poc_recommendation.model_dump()
    assert a.pitch_result.message_strategy == b.pitch_result.message_strategy


def test_does_not_persist_when_persist_false(db_session):
    from database.repository import list_leads

    pipeline.analyze(HIGH_LEAD, session=db_session, persist=False)
    assert list_leads(db_session) == []
