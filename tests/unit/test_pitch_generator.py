"""Unit tests for the Sales Pitch Generator."""

from database.models import LeadPriority, SignalType
from enrichment.poc_finder import POCFinder
from intelligence.lead_scorer import LeadScorer, LeadScoreResult
from intelligence.opportunity_analyzer import (
    OpportunityAnalyzer,
    OpportunityAssessment,
    OpportunityType,
)
from intelligence.signal_detector import SignalDetectionResult, SignalDetector
from outreach.pitch_generator import (
    MessageStrategy,
    PitchGenerationResult,
    PitchGenerator,
    run_pitch_generation,
)

gen = PitchGenerator()

FORBIDDEN = [
    "we guarantee",
    "we know you need",
    "we already work with",
    "your project requires",
    "you have a shortage",
]


def _sig(**kwargs) -> SignalDetectionResult:
    defaults = dict(
        signal_types=[SignalType.HIRING],
        signal_strength=70,
        signal_strength_label="MEDIUM",
        detected_technologies=["Java", "AWS"],
        detected_roles=["Java Engineer", "AWS Engineer"],
        estimated_hiring=None,
        project_value=None,
    )
    defaults.update(kwargs)
    return SignalDetectionResult(**defaults)


def _opp(opp_type: OpportunityType, confidence: int = 80) -> OpportunityAssessment:
    return OpportunityAssessment(
        opportunity_type=opp_type,
        opportunity_confidence=confidence,
        business_reason="Evidence-based reason.",
    )


def pitch(lead=None, opp_type=OpportunityType.LARGE_SCALE_RAMP_UP, poc=None, score=None, **sig_kwargs):
    return gen.generate(lead or {"company_name": "Acme"}, _sig(**sig_kwargs), _opp(opp_type), poc, score)


def _text(p: PitchGenerationResult) -> str:
    return " ".join(
        [p.email_subject, p.opening_message, p.value_proposition, p.recommended_pitch, p.call_to_action, p.linkedin_message]
        + p.call_talking_points
    ).lower()


# 1-8 opportunity-specific strategies ---------------------------------------
def test_normal_hiring_pitch():
    assert pitch(opp_type=OpportunityType.NORMAL_HIRING).message_strategy is MessageStrategy.HIRING_SUPPORT


def test_project_driven_hiring_pitch():
    assert pitch(opp_type=OpportunityType.PROJECT_DRIVEN_HIRING).message_strategy is MessageStrategy.PROJECT_RAMP_UP


def test_large_scale_ramp_up_pitch():
    assert pitch(opp_type=OpportunityType.LARGE_SCALE_RAMP_UP).message_strategy is MessageStrategy.SCALE_UP


def test_staff_augmentation_pitch():
    assert pitch(opp_type=OpportunityType.STAFF_AUGMENTATION).message_strategy is MessageStrategy.STAFF_AUGMENTATION


def test_vendor_opportunity_pitch():
    p = pitch(opp_type=OpportunityType.VENDOR_OPPORTUNITY, signal_types=[SignalType.VENDOR_REQUIREMENT])
    assert p.message_strategy is MessageStrategy.VENDOR_ONBOARDING
    assert "vendor" in p.call_to_action.lower()


def test_technology_implementation_pitch():
    assert pitch(opp_type=OpportunityType.TECHNOLOGY_IMPLEMENTATION).message_strategy is MessageStrategy.IMPLEMENTATION_DELIVERY


def test_digital_transformation_pitch():
    assert pitch(opp_type=OpportunityType.DIGITAL_TRANSFORMATION).message_strategy is MessageStrategy.TRANSFORMATION_DELIVERY


def test_low_confidence_nurture_pitch():
    p = pitch(opp_type=OpportunityType.LOW_CONFIDENCE, signal_types=[SignalType.OTHER], signal_strength=0, detected_technologies=[])
    assert p.message_strategy is MessageStrategy.NURTURE
    # No aggressive/hard claims in a nurture message.
    assert not any(f in _text(p) for f in FORBIDDEN)


# 9-12 industries -----------------------------------------------------------
def test_it_industry():
    p = pitch({"company_name": "Acme", "industry": "IT Services"})
    assert "engineering capacity" in p.value_proposition.lower() or "delivery scaling" in p.value_proposition.lower()


def test_bfsi_industry():
    p = pitch({"company_name": "NorthStar", "industry": "BFSI"})
    assert "modernization" in p.value_proposition.lower()


def test_fmcg_industry():
    p = pitch({"company_name": "Acme", "industry": "FMCG"})
    assert "platform" in p.value_proposition.lower() or "enterprise" in p.value_proposition.lower()


def test_healthcare_industry():
    p = pitch({"company_name": "Helios", "industry": "Healthcare"})
    assert "platform modernization" in p.value_proposition.lower() or "technology delivery" in p.value_proposition.lower()


# 13-14 personalization -----------------------------------------------------
def test_technology_personalization():
    p = pitch(detected_technologies=["Java", "AWS"])
    assert "java" in _text(p)


def test_poc_role_personalization():
    poc = POCFinder().recommend(
        {"industry": "BFSI"},
        _sig(signal_types=[SignalType.PROJECT_AWARD, SignalType.HIRING], estimated_hiring=45),
        _opp(OpportunityType.LARGE_SCALE_RAMP_UP),
    )
    p = gen.generate({"company_name": "NorthStar"}, _sig(), _opp(OpportunityType.LARGE_SCALE_RAMP_UP), poc)
    assert p.target_role is not None


def test_poc_role_from_enricher_title():
    class _FakePOC:
        class primary_contact:
            title = "VP of Engineering"
    p = gen.generate({"company_name": "Acme"}, _sig(), _opp(OpportunityType.STAFF_AUGMENTATION), _FakePOC())
    assert p.target_role == "VP of Engineering"


# 15-18 message components --------------------------------------------------
def test_email_subject_is_specific_not_generic():
    p = pitch()
    assert p.email_subject
    assert "business opportunity" not in p.email_subject.lower()
    assert len(p.email_subject) <= 90


def test_linkedin_message_length():
    p = pitch()
    assert p.linkedin_message
    assert len(p.linkedin_message) <= 500


def test_cta_varies_by_opportunity():
    vendor = pitch(opp_type=OpportunityType.VENDOR_OPPORTUNITY, signal_types=[SignalType.VENDOR_REQUIREMENT])
    ramp = pitch(opp_type=OpportunityType.LARGE_SCALE_RAMP_UP)
    assert vendor.call_to_action != ramp.call_to_action


def test_call_talking_points_count():
    p = pitch(signal_types=[SignalType.PROJECT_AWARD, SignalType.HIRING], estimated_hiring=45)
    assert 3 <= len(p.call_talking_points) <= 5


# 19 confidence -------------------------------------------------------------
def test_pitch_confidence_high():
    score = LeadScoreResult(score=90, priority=LeadPriority.HOT, scoring_confidence=90)
    poc = POCFinder().recommend(
        {"industry": "BFSI"},
        _sig(signal_types=[SignalType.PROJECT_AWARD, SignalType.HIRING], estimated_hiring=45),
        _opp(OpportunityType.LARGE_SCALE_RAMP_UP),
    )
    p = gen.generate(
        {"company_name": "NorthStar", "industry": "BFSI"},
        _sig(signal_strength=100, estimated_hiring=45),
        _opp(OpportunityType.LARGE_SCALE_RAMP_UP, 90),
        poc,
        score,
    )
    assert p.confidence >= 80
    assert p.confidence_label == "HIGH"


# 20 missing optional fields ------------------------------------------------
def test_missing_optional_fields():
    p = gen.generate(None, _sig(detected_technologies=[], detected_roles=[]), _opp(OpportunityType.NORMAL_HIRING))
    assert isinstance(p, PitchGenerationResult)
    assert p.email_subject and p.recommended_pitch


# 21 no fabrication ---------------------------------------------------------
def test_no_fabrication_of_hiring_numbers():
    p = pitch(estimated_hiring=None)
    assert not any(ch.isdigit() for ch in p.recommended_pitch)


def test_no_fabrication_of_technology():
    p = pitch(detected_technologies=[], detected_roles=[])
    # Should not name a specific technology that was not supplied.
    assert "java" not in _text(p) and "aws" not in _text(p)


def test_no_forbidden_language():
    for opp_type in OpportunityType:
        p = pitch(opp_type=opp_type)
        assert not any(f in _text(p) for f in FORBIDDEN)


# 22 determinism ------------------------------------------------------------
def test_deterministic_repeated_execution():
    a = pitch(signal_types=[SignalType.PROJECT_AWARD, SignalType.HIRING], estimated_hiring=30)
    b = pitch(signal_types=[SignalType.PROJECT_AWARD, SignalType.HIRING], estimated_hiring=30)
    assert a.model_dump() == b.model_dump()


# 23 length constraints -----------------------------------------------------
def test_output_length_constraints():
    p = pitch(signal_types=[SignalType.PROJECT_AWARD, SignalType.HIRING], estimated_hiring=45)
    words = len(p.recommended_pitch.split())
    assert 30 <= words <= 220
    assert len(p.linkedin_message) <= 500
    assert 3 <= len(p.call_talking_points) <= 5


def test_serializes_to_strings():
    p = pitch()
    payload = p.model_dump(mode="json")
    assert payload["message_strategy"] in {s.value for s in MessageStrategy}


def test_convenience_wrapper():
    assert isinstance(run_pitch_generation({"company_name": "Acme"}, _sig(), _opp(OpportunityType.NORMAL_HIRING)), PitchGenerationResult)


# 20 integration: full stack ------------------------------------------------
def test_integration_full_stack():
    text = (
        "Company won a major banking transformation project and is hiring "
        "30 Java engineers, 10 AWS engineers and 5 DevOps specialists."
    )
    lead = {"company_name": "NorthStar", "industry": "BFSI", "signal_description": text}
    signal = SignalDetector().detect(signal_description=text)
    opportunity = OpportunityAnalyzer().analyze(lead, signal)
    score = LeadScorer().score(lead, signal, opportunity)
    poc = POCFinder().recommend(lead, signal, opportunity)
    result = gen.generate(lead, signal, opportunity, poc, score)

    assert signal.signal_types
    assert opportunity.opportunity_type
    assert "NorthStar" in result.email_subject or "NorthStar" in result.recommended_pitch
    assert result.target_role is not None
    assert result.message_strategy is MessageStrategy.SCALE_UP
    assert result.confidence_label in {"MEDIUM", "HIGH"}
    assert "java" in _text(result)
