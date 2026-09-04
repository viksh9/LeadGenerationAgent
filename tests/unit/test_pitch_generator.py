"""Unit tests for the PitchGenerator engine."""

from enrichment.poc_finder import POCEnricher
from intelligence.opportunity_analyzer import (
    OpportunityAnalyzer,
    OpportunityAssessment,
    OpportunityType,
    Urgency,
)
from intelligence.lead_scorer import LeadScorer
from intelligence.signal_detector import SignalDetectionResult, SignalDetector
from database.models import LeadPriority, SignalType
from outreach.pitch_generator import (
    GeneratedPitchResult,
    PitchGenerator,
    PitchTone,
    run_pitch_generation,
)

generator = PitchGenerator()


def _opp(opp_type=OpportunityType.LARGE_SCALE_RAMP_UP, urgency=Urgency.HIGH, reason="Evidence."):
    return OpportunityAssessment(
        opportunity_type=opp_type, urgency=urgency, business_reason=reason
    )


def _sig(**kwargs) -> SignalDetectionResult:
    defaults = dict(signal_types=[SignalType.HIRING], detected_technologies=["Java", "AWS"], estimated_hiring=45)
    defaults.update(kwargs)
    return SignalDetectionResult(**defaults)


def test_generates_subject_body_and_angle():
    pitch = generator.generate({"company_name": "NorthStar"}, _opp(), _sig())
    assert isinstance(pitch, GeneratedPitchResult)
    assert "NorthStar" in pitch.subject
    assert pitch.body
    assert pitch.angle
    assert pitch.call_to_action
    assert pitch.talking_points


def test_technologies_and_team_size_are_woven_in():
    pitch = generator.generate({"company_name": "NorthStar"}, _opp(), _sig(estimated_hiring=45))
    joined = pitch.subject + " " + pitch.body
    assert "Java" in joined
    assert "45" in pitch.body


def test_no_technologies_falls_back_to_engineering():
    pitch = generator.generate({"company_name": "Acme"}, _opp(), _sig(detected_technologies=[], estimated_hiring=None))
    assert "engineering" in (pitch.subject + pitch.body).lower()
    assert "additional" in pitch.body.lower()  # team phrase fallback


def test_angle_varies_by_opportunity_type():
    ramp = generator.generate({"company_name": "A"}, _opp(OpportunityType.LARGE_SCALE_RAMP_UP), _sig())
    vendor = generator.generate({"company_name": "A"}, _opp(OpportunityType.VENDOR_OPPORTUNITY), _sig())
    assert ramp.angle != vendor.angle


def test_greeting_uses_known_contact_first_name():
    lead = {"company_name": "NorthStar", "contacts": [{"full_name": "Priya Raman", "title": "VP of Engineering"}]}
    poc = POCEnricher().enrich(lead, None, _opp(OpportunityType.LARGE_SCALE_RAMP_UP))
    pitch = generator.generate(lead, _opp(), _sig(), poc=poc)
    assert pitch.body.startswith("Hi Priya,")
    assert pitch.target_persona == "VP of Engineering"


def test_greeting_falls_back_to_company_team():
    pitch = generator.generate({"company_name": "NorthStar"}, _opp(), _sig())
    assert "Hello NorthStar team," in pitch.body


def test_tone_direct_for_high_urgency():
    pitch = generator.generate({"company_name": "A"}, _opp(urgency=Urgency.CRITICAL), _sig())
    assert pitch.tone is PitchTone.DIRECT


def test_tone_nurture_for_low_confidence():
    pitch = generator.generate(
        {"company_name": "A"}, _opp(OpportunityType.LOW_CONFIDENCE, urgency=Urgency.LOW), _sig()
    )
    assert pitch.tone is PitchTone.NURTURE


def test_deterministic():
    a = generator.generate({"company_name": "NorthStar"}, _opp(), _sig())
    b = generator.generate({"company_name": "NorthStar"}, _opp(), _sig())
    assert a.model_dump() == b.model_dump()


def test_missing_company_name():
    pitch = generator.generate(None, _opp(), _sig())
    assert "your company" in pitch.subject.lower() or pitch.subject


def test_serializes_to_strings():
    pitch = generator.generate({"company_name": "A"}, _opp(), _sig())
    payload = pitch.model_dump(mode="json")
    assert payload["tone"] in {t.value for t in PitchTone}
    assert isinstance(payload["talking_points"], list)


def test_convenience_wrapper():
    pitch = run_pitch_generation({"company_name": "A"}, _opp(), _sig())
    assert isinstance(pitch, GeneratedPitchResult)


def test_integration_full_stack():
    text = (
        "Company won a major banking transformation project and is hiring "
        "30 Java engineers, 10 AWS engineers and 5 DevOps specialists."
    )
    lead = {"company_name": "NorthStar", "signal_description": text}
    signal = SignalDetector().detect(signal_description=text)
    opportunity = OpportunityAnalyzer().analyze(lead, signal)
    score = LeadScorer().score(lead, signal, opportunity)
    poc = POCEnricher().enrich(lead, signal, opportunity)
    pitch = generator.generate(lead, opportunity, signal, score, poc)

    assert "NorthStar" in pitch.subject
    assert pitch.tone is PitchTone.DIRECT  # HOT / high urgency
    assert "Java" in pitch.body
