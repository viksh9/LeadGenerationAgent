from outreach.pitch_generator import generate_pitch
from intelligence.lead_scorer import LeadScore
from intelligence.opportunity_analyzer import OpportunityInsight
from processors.normalizer import normalize_record
from collectors.base import RawCompanyRecord, RawSignal


def test_normalize_drops_unknown_signal_types():
    record = RawCompanyRecord(
        name=" Acme ",
        signals=[
            RawSignal(signal_type="rumor", title="Heard something"),
            RawSignal(signal_type="hiring", title="Hiring CTO"),
        ],
    )
    normalized = normalize_record(record)
    assert normalized is not None
    assert normalized.name == "Acme"
    assert len(normalized.signals) == 1
    assert normalized.signals[0].signal_type == "hiring"


def test_generate_pitch_includes_company_and_score():
    pitch = generate_pitch(
        company_name="Helios Health",
        opportunity=OpportunityInsight(
            summary="Helios Health shows budgeted growth intent.",
            recommended_motion="Executive briefing on scale-up",
            primary_stage="budgeted_growth",
            pain_hypotheses=["Systems integration is a near-term delivery risk."],
        ),
        score=LeadScore(score=72, intent_level="high", reasons=[]),
        contact_name="Alex Kim",
        contact_title="CTO",
    )
    assert "Helios Health" in pitch.subject or "Helios Health" in pitch.body
    assert "72" in pitch.body
    assert pitch.angle == "Executive briefing on scale-up"
