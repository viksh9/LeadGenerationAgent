"""Unit tests for the LeadScorer engine (8-category model)."""

from datetime import datetime, timedelta, timezone

from database.models import LeadPriority, SignalType
from intelligence.lead_scorer import (
    LeadScorer,
    LeadScoreResult,
    ScoringConfig,
    default_scoring_config,
    run_lead_scoring,
)
from intelligence.opportunity_analyzer import OpportunityAnalyzer
from intelligence.signal_detector import SignalDetectionResult, SignalDetector

scorer = LeadScorer()
NOW = datetime(2026, 9, 4, tzinfo=timezone.utc)


def _sig(**kwargs) -> SignalDetectionResult:
    defaults = dict(
        signal_types=[SignalType.HIRING],
        signal_strength=50,
        signal_strength_label="MEDIUM",
        detected_technologies=[],
        detected_roles=[],
        estimated_hiring=None,
        project_value=None,
        detected_keywords=[],
    )
    defaults.update(kwargs)
    return SignalDetectionResult(**defaults)


def score(lead=None, **sig_kwargs) -> LeadScoreResult:
    return scorer.score(lead or {}, _sig(**sig_kwargs), None, now=NOW)


def _recent(days: int) -> datetime:
    return NOW - timedelta(days=days)


# 1-4 priority tiers --------------------------------------------------------
def test_hot_lead():
    result = score(
        {"industry": "BFSI", "poc_name": "P", "poc_title": "VP", "signal_date": _recent(2)},
        signal_types=[SignalType.PROJECT_AWARD, SignalType.HIRING, SignalType.DIGITAL_TRANSFORMATION],
        signal_strength=100,
        estimated_hiring=45,
        detected_technologies=["Java", "AWS", "DevOps"],
        detected_roles=["Java Engineer", "AWS Engineer", "DevOps Specialist"],
    )
    assert result.priority is LeadPriority.HOT
    assert result.score >= 80


def test_warm_lead():
    result = score(
        {"industry": "BFSI", "signal_date": _recent(3), "poc_name": "P", "poc_title": "VP"},
        signal_types=[SignalType.PROJECT_AWARD, SignalType.HIRING],
        signal_strength=80,
        estimated_hiring=12,
        detected_technologies=["Java", "AWS", "DevOps"],
        detected_roles=["Java Engineer", "AWS Engineer", "DevOps Engineer"],
    )
    assert result.priority is LeadPriority.WARM
    assert 60 <= result.score < 80


def test_nurture_lead():
    result = score(
        {"industry": "BFSI", "signal_date": _recent(5), "poc_title": "Manager"},
        signal_types=[SignalType.HIRING],
        signal_strength=45,
        estimated_hiring=10,
        detected_technologies=["Java", "AWS", "DevOps"],
        detected_roles=["Java Engineer", "AWS Engineer", "DevOps Engineer"],
    )
    assert result.priority is LeadPriority.NURTURE
    assert 40 <= result.score < 60


def test_low_lead():
    result = score(signal_types=[SignalType.HIRING], signal_strength=15)
    assert result.priority is LeadPriority.LOW
    assert result.score < 40


# 5-6 hiring ----------------------------------------------------------------
def test_large_technology_hiring():
    result = score(estimated_hiring=45)
    assert result.score_breakdown["large_technology_hiring"] == 20


def test_small_technology_hiring():
    result = score(estimated_hiring=1)
    assert 0 < result.score_breakdown["large_technology_hiring"] <= 5


# 7-8 project ---------------------------------------------------------------
def test_project_award():
    result = score(signal_types=[SignalType.PROJECT_AWARD])
    assert result.score_breakdown["new_project_or_contract"] == 20


def test_project_execution():
    result = score(signal_types=[SignalType.PROJECT_EXECUTION])
    assert result.score_breakdown["new_project_or_contract"] == 12


def test_project_evidence_is_not_double_counted():
    both = score(signal_types=[SignalType.PROJECT_AWARD, SignalType.CONTRACT, SignalType.PROJECT_EXECUTION])
    # Strongest single project signal only, not the sum.
    assert both.score_breakdown["new_project_or_contract"] == 20


# 9-10 enterprise / government ----------------------------------------------
def test_enterprise_project():
    result = score({"industry": "BFSI", "company_size": "1001-5000"})
    assert result.score_breakdown["enterprise_project"] > 0


def test_government_project():
    result = score({"signal_description": "Public sector government tender awarded."})
    assert result.score_breakdown["enterprise_project"] > 0


def test_not_every_company_is_enterprise():
    result = score({"industry": "Local Cafe", "company_size": "1-50"})
    assert result.score_breakdown["enterprise_project"] == 0


# 11 multiple openings ------------------------------------------------------
def test_multiple_technology_openings():
    few = score(detected_technologies=["Java"], detected_roles=["Java Engineer"])
    many = score(
        detected_technologies=["Java", "AWS", "DevOps", "React"],
        detected_roles=["Java Engineer", "AWS Engineer", "DevOps Engineer", "Frontend Engineer"],
    )
    assert many.score_breakdown["multiple_openings"] > few.score_breakdown["multiple_openings"]


# 12 transformation ---------------------------------------------------------
def test_digital_transformation():
    result = score(signal_types=[SignalType.DIGITAL_TRANSFORMATION])
    assert result.score_breakdown["expansion_or_transformation"] > 0


# 13 technology match -------------------------------------------------------
def test_technology_stack_matching():
    result = score(detected_technologies=["Java", "AWS", "DevOps", "Kubernetes"])
    assert result.score_breakdown["technology_match"] == 10  # capped
    none = score(detected_technologies=["Cobol"])  # not in relevant set
    assert none.score_breakdown["technology_match"] == 0


# 14 decision-maker ---------------------------------------------------------
def test_decision_maker_available():
    result = score({"poc_name": "Priya", "poc_title": "VP Engineering", "poc_linkedin_url": "x"})
    assert result.score_breakdown["decision_maker"] == 5
    assert score({}).score_breakdown["decision_maker"] == 0


# 15-17 recency -------------------------------------------------------------
def test_recent_signal():
    assert score({"signal_date": _recent(3)}).score_breakdown["recency"] == 5


def test_old_signal():
    assert score({"signal_date": _recent(200)}).score_breakdown["recency"] == 0


def test_missing_signal_date():
    assert score({}).score_breakdown["recency"] == 0


def test_future_signal_date_not_counted():
    assert score({"signal_date": NOW + timedelta(days=5)}).score_breakdown["recency"] == 0


# 18-21 missing inputs ------------------------------------------------------
def test_missing_project():
    assert score(signal_types=[SignalType.HIRING]).score_breakdown["new_project_or_contract"] == 0


def test_missing_hiring_information():
    assert score(estimated_hiring=None).score_breakdown["large_technology_hiring"] == 0


def test_missing_technologies():
    assert score(detected_technologies=[]).score_breakdown["technology_match"] == 0


def test_missing_poc():
    assert score({}).score_breakdown["decision_maker"] == 0


# 22-25 boundaries ----------------------------------------------------------
def test_score_exactly_zero():
    result = scorer.score({}, _sig(signal_types=[SignalType.OTHER], signal_strength=0), now=NOW)
    assert result.score == 0
    assert result.priority is LeadPriority.LOW


def test_score_can_reach_100():
    result = score(
        {
            "industry": "Government",
            "company_size": "10000+",
            "project_value": 5_000_000,
            "signal_description": "government tender",
            "poc_name": "P",
            "poc_title": "CTO",
            "poc_linkedin_url": "x",
            "signal_date": _recent(1),
        },
        signal_types=[
            SignalType.PROJECT_AWARD,
            SignalType.DIGITAL_TRANSFORMATION,
            SignalType.EXPANSION,
        ],
        signal_strength=100,
        estimated_hiring=100,
        detected_technologies=["Java", "AWS", "DevOps", "React"],
        detected_roles=["Java Engineer", "AWS Engineer", "DevOps Engineer", "Frontend Engineer"],
    )
    assert result.score == 100


def test_score_never_exceeds_100():
    result = score(
        {
            "industry": "Government",
            "company_size": "99999",
            "project_value": 10 ** 12,
            "signal_description": "government tender ministry federal",
            "poc_name": "P",
            "poc_title": "CTO",
            "poc_linkedin_url": "x",
            "signal_date": _recent(0),
        },
        signal_types=list(SignalType),
        signal_strength=100,
        estimated_hiring=100000,
        detected_technologies=["Java"] * 40,
        detected_roles=["Java Engineer"] * 40,
    )
    assert result.score <= 100
    assert all(v <= m for v, m in zip(
        result.score_breakdown.values(), [20, 20, 15, 15, 10, 10, 5, 5]
    ))


def test_breakdown_sums_to_score():
    result = score(
        {"industry": "BFSI", "signal_date": _recent(5), "poc_name": "P", "poc_title": "VP"},
        signal_types=[SignalType.PROJECT_AWARD, SignalType.HIRING],
        estimated_hiring=30,
        detected_technologies=["Java", "AWS"],
        detected_roles=["Java Engineer", "AWS Engineer"],
    )
    assert sum(result.score_breakdown.values()) == result.score


# 26 duplicate evidence -----------------------------------------------------
def test_duplicate_technologies_do_not_inflate():
    a = score(detected_technologies=["Java", "AWS"])
    b = score(detected_technologies=["Java", "Java", "AWS", "AWS"])
    assert a.score_breakdown["technology_match"] == b.score_breakdown["technology_match"]


# 27 determinism ------------------------------------------------------------
def test_deterministic_repeated_execution():
    lead = {"industry": "BFSI", "signal_date": _recent(3), "poc_name": "P"}
    kwargs = dict(signal_types=[SignalType.PROJECT_AWARD, SignalType.HIRING], estimated_hiring=20, detected_technologies=["Java", "AWS"])
    first = scorer.score(lead, _sig(**kwargs), None, now=NOW)
    second = scorer.score(lead, _sig(**kwargs), None, now=NOW)
    assert first.model_dump() == second.model_dump()


# structured output ---------------------------------------------------------
def test_positive_and_negative_signals_and_explanation():
    result = score(
        {"industry": "BFSI", "signal_date": _recent(2), "poc_name": "P", "poc_title": "VP"},
        signal_types=[SignalType.PROJECT_AWARD, SignalType.HIRING],
        estimated_hiring=30,
        detected_technologies=["Java", "AWS"],
        detected_roles=["Java Engineer", "AWS Engineer"],
    )
    assert any("hiring" in s.lower() for s in result.positive_signals)
    assert result.explanation
    assert isinstance(result.negative_signals, list)


def test_scoring_confidence():
    strong = score(
        {"source_name": "press release", "signal_date": _recent(2)},
        signal_types=[SignalType.PROJECT_AWARD, SignalType.HIRING],
        signal_strength=100,
        estimated_hiring=45,
        detected_technologies=["Java", "AWS"],
    )
    assert strong.scoring_confidence_label == "HIGH"
    weak = score(signal_types=[SignalType.OTHER], signal_strength=0)
    assert weak.scoring_confidence_label == "LOW"
    assert 0 <= strong.scoring_confidence <= 100


def test_configurable_weights():
    tight = LeadScorer(ScoringConfig(large_hiring_max=5))
    result = tight.score({}, _sig(estimated_hiring=100), now=NOW)
    assert result.score_breakdown["large_technology_hiring"] == 5


def test_default_config():
    assert default_scoring_config().large_hiring_max == 20


def test_convenience_wrapper():
    result = run_lead_scoring({}, _sig(estimated_hiring=10), now=NOW)
    assert isinstance(result, LeadScoreResult)


# §13 low-score scenario ----------------------------------------------------
def test_scenario_office_administrator_is_low():
    detection = SignalDetector().detect(signal_description="Company is hiring one office administrator.")
    result = scorer.score({"signal_description": "Company is hiring one office administrator."}, detection, now=NOW)
    assert result.priority in {LeadPriority.LOW, LeadPriority.NURTURE}
    assert result.score < 40


# §16 integration: detector -> analyzer -> scorer ---------------------------
def test_integration_detector_analyzer_scorer():
    text = (
        "Won a major banking modernization project and is hiring "
        "30 Java engineers, 10 AWS engineers and 5 DevOps specialists."
    )
    lead = {
        "company_name": "NorthStar Banking Technologies",
        "industry": "BFSI",
        "signal_description": text,
        "poc_name": "Priya Raman",
        "poc_title": "VP of Engineering",
        "signal_date": _recent(3),
    }
    signal = SignalDetector().detect(signal_description=text)
    opportunity = OpportunityAnalyzer().analyze(lead, signal)
    result = scorer.score(lead, signal, opportunity, now=NOW)

    assert signal.signal_types  # signals detected
    assert opportunity.opportunity_type  # opportunity analyzed
    assert result.priority is LeadPriority.HOT
    assert sum(result.score_breakdown.values()) == result.score
    assert result.explanation
