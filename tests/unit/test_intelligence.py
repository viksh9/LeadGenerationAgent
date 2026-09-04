from datetime import datetime, timezone

from intelligence.lead_scorer import score_lead
from intelligence.opportunity_analyzer import analyze_opportunity
from intelligence.signal_detector import detect_signals
from processors.normalizer import NormalizedSignal


def _signal(**kwargs) -> NormalizedSignal:
    defaults = dict(
        signal_type="hiring",
        title="Hiring Head of Data Platform",
        description="Replace spreadsheets with a routing platform.",
        source="careers",
        source_url=None,
        strength=0.8,
        observed_at=datetime(2026, 8, 28, tzinfo=timezone.utc),
    )
    defaults.update(kwargs)
    return NormalizedSignal(**defaults)


def test_detect_signals_tags_and_boosts_recent_hiring():
    detected = detect_signals([_signal()])
    assert detected[0].signal_type == "hiring"
    assert "hiring_buildout" in detected[0].intent_tags
    assert detected[0].buying_stage == "building_capacity"
    assert detected[0].strength >= 0.8


def test_score_lead_rewards_corroborating_categories():
    signals = detect_signals(
        [
            _signal(),
            _signal(
                signal_type="project",
                title="Warehouse automation RFP",
                description="Inventory visibility RFP across 12 warehouses.",
                strength=0.92,
            ),
        ]
    )
    scored = score_lead(signals)
    assert scored.score >= 60
    assert scored.intent_level in {"medium", "high", "critical"}
    assert any("corroborate" in reason.lower() or "categories" in reason.lower() for reason in scored.reasons)


def test_score_lead_empty():
    scored = score_lead([])
    assert scored.score == 0
    assert scored.intent_level == "low"


def test_opportunity_analyzer_picks_evaluation_for_rfp():
    signals = detect_signals(
        [
            _signal(
                signal_type="project",
                title="Warehouse automation RFP",
                description="Formal RFP for inventory visibility.",
                strength=0.9,
            )
        ]
    )
    insight = analyze_opportunity("Northwind Logistics", signals)
    assert insight.primary_stage == "evaluation"
    assert "workshop" in insight.recommended_motion.lower() or "RFP" in insight.recommended_motion
    assert insight.pain_hypotheses
