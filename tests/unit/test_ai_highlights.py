"""AI Profile Highlights (Prompt 50, §15-§18, §40-§42). No DB — in-memory objects."""

from __future__ import annotations

from database.models import (
    AIAnalysisStatus,
    AIIntelligenceResult,
    DataProvenance,
    Lead,
    LeadPriority,
    LeadStatus,
    SignalType,
)
from ai.highlights import build_profile_highlights, evidence_trust_level
from intelligence.opportunity_view import derive_opportunity_view


def _lead() -> Lead:
    return Lead(company_name="Acme Tech", normalized_company_name="acme tech", lead_score=85,
                lead_priority=LeadPriority.HOT, status=LeadStatus.NEW, signal_type=SignalType.HIRING,
                estimated_hiring=47, it_job_count=47, technologies=["Java", "AWS", "AI"],
                data_provenance=DataProvenance.REAL)


def _ai(**kw) -> AIIntelligenceResult:
    base = dict(subject_type="LEAD", subject_id=1, ai_generated=True,
                analysis_status=AIAnalysisStatus.AI_VALIDATED, executive_summary="Strong engineering hiring.",
                evidence_ids=[1, 2], source_ids=["Official Career Site", "Adzuna"],
                inferred_insights=[], verified_facts=[], model_name="test-model", data_provenance=DataProvenance.REAL)
    base.update(kw)
    return AIIntelligenceResult(**base)


def test_trust_levels():
    assert evidence_trust_level(source_ids=["Official Career Site", "Adzuna"], source_count=2) == "HIGH"
    assert evidence_trust_level(source_ids=["Official Career Site"], source_count=1) == "MEDIUM"
    assert evidence_trust_level(source_ids=["Adzuna", "Jooble"], source_count=2) == "MEDIUM"
    assert evidence_trust_level(source_ids=["Adzuna"], source_count=1) == "LOW"


def test_deterministic_highlights_always_present():
    lead = _lead()
    ov = derive_opportunity_view(lead)
    h = build_profile_highlights(lead, ai_result=None, opportunity=ov,
                                 source_ids=["Official Career Site"], source_count=1)
    titles = [x.highlight_title for x in h.highlights]
    assert "Hiring Trend" in titles and "Technology Focus" in titles and "Hiring Signal" in titles
    assert "Potential Opportunity" in titles


def test_no_ai_result_means_unavailable_no_fake_prose():
    h = build_profile_highlights(_lead(), ai_result=None, source_ids=["Adzuna"], source_count=1)
    assert h.ai_available is False
    assert h.ai_insight is None
    assert not any(x.highlight_title == "AI Insight" for x in h.highlights)


def test_deterministic_result_not_treated_as_ai():
    ai = _ai(ai_generated=False, analysis_status=AIAnalysisStatus.DETERMINISTIC)
    h = build_profile_highlights(_lead(), ai_result=ai, source_ids=["Adzuna"], source_count=1)
    assert h.ai_available is False and h.ai_insight is None


def test_ai_insight_surfaced_when_generated_and_validated():
    h = build_profile_highlights(_lead(), ai_result=_ai(), source_ids=["Official Career Site", "Adzuna"], source_count=2)
    assert h.ai_available is True
    assert h.ai_insight == "Strong engineering hiring."
    assert any(x.highlight_title == "AI Insight" and x.ai_generated for x in h.highlights)


def test_unsupported_insight_is_skipped():
    ai = _ai(executive_summary="", inferred_insights=[
        {"claim_text": "Company plans to hire 500 people", "validation_status": "UNSUPPORTED_CLAIM"},
        {"claim_text": "Active engineering hiring observed", "validation_status": None},
    ])
    h = build_profile_highlights(_lead(), ai_result=ai, source_ids=["Official Career Site", "Adzuna"], source_count=2)
    assert h.ai_insight == "Active engineering hiring observed"      # unsupported claim rejected


def test_all_unsupported_and_empty_summary_stays_unavailable():
    ai = _ai(executive_summary="", inferred_insights=[
        {"claim_text": "fabricated", "validation_status": "UNSUPPORTED_CLAIM"}])
    h = build_profile_highlights(_lead(), ai_result=ai, source_ids=["Adzuna"], source_count=1)
    assert h.ai_available is False and h.ai_insight is None
