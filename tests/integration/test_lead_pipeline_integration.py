"""Integration test: raw lead -> full pipeline -> database.

Self-contained (its own throwaway SQLite DB) so it never touches the real
development database, and does not depend on tests/unit fixtures.
"""

from datetime import datetime, timedelta, timezone

from database.models import LeadPriority, LeadStatus, SignalType
from database.repository import create_session_factory, get_engine, get_lead, init_db
from intelligence.lead_pipeline import LeadAnalysisPipeline


def _session(tmp_path):
    engine = get_engine(f"sqlite:///{tmp_path / 'integration.db'}")
    init_db(engine)
    return create_session_factory(engine)()


def test_end_to_end_pipeline_persists_correct_record(tmp_path):
    session = _session(tmp_path)
    pipeline = LeadAnalysisPipeline()
    raw = {
        "company_name": "NorthStar Banking Technologies",
        "industry": "BFSI",
        "signal_title": "Digital Banking Transformation",
        "signal_description": (
            "The company recently won a major banking modernization project and is hiring "
            "30 Java engineers, 10 AWS engineers and 5 DevOps specialists."
        ),
        "technologies": ["Java", "Spring Boot", "AWS", "DevOps"],
        "estimated_hiring": 45,
        "signal_date": datetime.now(timezone.utc) - timedelta(days=2),
        "poc_name": "Priya Raman",
        "poc_title": "VP of Engineering",
        "source_url": "https://news.example/northstar",
    }

    result = pipeline.analyze(raw, session=session, persist=True)

    # Each stage produced output.
    assert {SignalType.PROJECT_AWARD, SignalType.HIRING, SignalType.DIGITAL_TRANSFORMATION}.issubset(
        set(result.signal_analysis.signal_types)
    )
    assert result.opportunity_analysis.opportunity_type is not None
    assert result.priority is LeadPriority.HOT
    assert result.final_score >= 80
    assert result.poc_recommendation.primary_role is not None
    assert result.pitch_result.email_subject

    # Record persisted correctly.
    assert result.lead_id and result.lead_id > 0
    stored = get_lead(session, result.lead_id)
    assert stored is not None
    assert stored.company_name == "NorthStar Banking Technologies"
    assert stored.industry == "BFSI"
    assert stored.lead_priority is LeadPriority.HOT
    assert stored.status is LeadStatus.NEW
    assert stored.estimated_hiring == 45
    assert {"Java", "AWS", "DevOps"}.issubset(set(stored.technologies))
    assert stored.opportunity_summary
    assert stored.recommended_action
    assert stored.recommended_pitch

    session.close()
