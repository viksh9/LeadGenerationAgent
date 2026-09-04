"""Unit tests for the OpportunityAnalyzer engine."""

from database.models import SignalType
from intelligence.opportunity_analyzer import (
    OpportunityAnalyzer,
    OpportunityAssessment,
    OpportunityType,
    StaffingNeed,
    Urgency,
    run_opportunity_analysis,
)
from intelligence.signal_detector import SignalDetectionResult, SignalDetector

analyzer = OpportunityAnalyzer()


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


def analyze(lead_data=None, **sig_kwargs) -> OpportunityAssessment:
    return analyzer.analyze(lead_data, _sig(**sig_kwargs))


# 1 -------------------------------------------------------------------------
def test_normal_hiring():
    result = analyze(signal_types=[SignalType.HIRING], estimated_hiring=1, signal_strength=20)
    assert result.opportunity_type is OpportunityType.NORMAL_HIRING
    assert result.potential_staffing_need is StaffingNeed.LOW


# 2 -------------------------------------------------------------------------
def test_project_driven_hiring():
    result = analyze(
        signal_types=[SignalType.PROJECT_AWARD, SignalType.HIRING],
        estimated_hiring=8,
        signal_strength=70,
    )
    assert result.opportunity_type is OpportunityType.PROJECT_DRIVEN_HIRING


# 3 -------------------------------------------------------------------------
def test_large_scale_ramp_up():
    result = analyze(
        signal_types=[SignalType.PROJECT_AWARD, SignalType.HIRING],
        estimated_hiring=45,
        detected_technologies=["Java", "AWS", "DevOps"],
        signal_strength=100,
    )
    assert result.opportunity_type is OpportunityType.LARGE_SCALE_RAMP_UP
    assert OpportunityType.PROJECT_DRIVEN_HIRING in result.secondary_opportunity_types
    assert result.potential_staffing_need is StaffingNeed.HIGH


# 4 -------------------------------------------------------------------------
def test_staff_augmentation():
    result = analyze(
        lead_data={"signal_description": "During project execution we need staff augmentation and external resources."},
        signal_types=[SignalType.PROJECT_EXECUTION, SignalType.VENDOR_REQUIREMENT],
        signal_strength=70,
    )
    assert result.opportunity_type is OpportunityType.STAFF_AUGMENTATION


# 5 -------------------------------------------------------------------------
def test_vendor_opportunity():
    result = analyze(
        lead_data={"signal_description": "Seeking an implementation partner and outsourcing vendor."},
        signal_types=[SignalType.VENDOR_REQUIREMENT],
        signal_strength=60,
    )
    assert result.opportunity_type is OpportunityType.VENDOR_OPPORTUNITY
    assert "procurement" in result.recommended_next_step.lower()


# 6 -------------------------------------------------------------------------
def test_technology_implementation():
    result = analyze(
        lead_data={"signal_description": "AI initiative with a large implementation and migration of the data platform."},
        signal_types=[SignalType.TECHNOLOGY_INITIATIVE, SignalType.PROJECT_EXECUTION],
        detected_technologies=["AI"],
        signal_strength=65,
    )
    assert result.opportunity_type is OpportunityType.TECHNOLOGY_IMPLEMENTATION


# 7 -------------------------------------------------------------------------
def test_digital_transformation():
    result = analyze(
        signal_types=[SignalType.DIGITAL_TRANSFORMATION, SignalType.HIRING],
        detected_technologies=["AWS", "Kubernetes"],
        estimated_hiring=15,
        signal_strength=75,
    )
    assert result.opportunity_type is OpportunityType.DIGITAL_TRANSFORMATION


# 8 -------------------------------------------------------------------------
def test_low_confidence_opportunity():
    result = analyze(signal_types=[SignalType.OTHER], signal_strength=0)
    assert result.opportunity_type is OpportunityType.LOW_CONFIDENCE
    assert result.potential_staffing_need is StaffingNeed.LOW
    assert result.opportunity_confidence_label == "LOW"


# 9, 10, 11 -----------------------------------------------------------------
def test_high_staffing_need():
    result = analyze(
        signal_types=[SignalType.PROJECT_AWARD, SignalType.HIRING],
        estimated_hiring=40,
        detected_technologies=["Java", "AWS"],
        signal_strength=95,
    )
    assert result.potential_staffing_need is StaffingNeed.HIGH


def test_medium_staffing_need():
    result = analyze(
        lead_data={"signal_description": "Seeking a delivery partner / vendor."},
        signal_types=[SignalType.VENDOR_REQUIREMENT],
        signal_strength=55,
    )
    assert result.potential_staffing_need is StaffingNeed.MEDIUM


def test_low_staffing_need():
    result = analyze(signal_types=[SignalType.HIRING], estimated_hiring=1, signal_strength=15)
    assert result.potential_staffing_need is StaffingNeed.LOW


# 12 ------------------------------------------------------------------------
def test_role_detection():
    result = analyze(
        signal_types=[SignalType.HIRING],
        detected_technologies=["Java", "AWS", "DevOps"],
        estimated_hiring=10,
    )
    roles = set(result.likely_roles)
    assert "Java Engineer" in roles or "Java Developer" in roles
    assert "AWS Engineer" in roles
    assert "DevOps Engineer" in roles


def test_roles_exclude_unrelated():
    result = analyze(signal_types=[SignalType.HIRING], detected_technologies=["Java"], estimated_hiring=3)
    assert all("Java" in r or "Engineer" in r or "Developer" in r for r in result.likely_roles)


# 13 ------------------------------------------------------------------------
def test_technology_reuse_from_detector():
    techs = ["Java", "AWS", "DevOps"]
    result = analyze(signal_types=[SignalType.HIRING], detected_technologies=techs, estimated_hiring=5)
    assert result.likely_technologies == techs  # reused verbatim, not re-detected


# 14 ------------------------------------------------------------------------
def test_team_size_estimation_explicit():
    result = analyze(signal_types=[SignalType.HIRING], estimated_hiring=40, signal_strength=60)
    assert result.estimated_team_size_min == 40
    assert result.estimated_team_size_max == 40


def test_team_size_null_when_unquantified():
    result = analyze(
        lead_data={"signal_description": "Expanding the engineering team significantly."},
        signal_types=[SignalType.HIRING],
        estimated_hiring=None,
    )
    assert result.estimated_team_size_min is None
    assert result.estimated_team_size_max is None


# 15 ------------------------------------------------------------------------
def test_urgency_high_for_award_plus_large_hiring():
    result = analyze(
        signal_types=[SignalType.PROJECT_AWARD, SignalType.HIRING],
        estimated_hiring=45,
        signal_strength=100,
    )
    assert result.urgency in {Urgency.HIGH, Urgency.CRITICAL}


def test_urgency_critical_with_immediate_language():
    result = analyze(
        lead_data={"signal_description": "Project awarded last week and hiring 50 engineers immediately."},
        signal_types=[SignalType.PROJECT_AWARD, SignalType.HIRING],
        estimated_hiring=50,
        signal_strength=100,
    )
    assert result.urgency is Urgency.CRITICAL


def test_urgency_low_for_single_opening():
    result = analyze(signal_types=[SignalType.HIRING], estimated_hiring=1, signal_strength=15)
    assert result.urgency in {Urgency.LOW, Urgency.MEDIUM}


def test_urgency_unknown_without_signals():
    result = analyze(signal_types=[SignalType.OTHER], signal_strength=0)
    assert result.urgency is Urgency.UNKNOWN


# 16 ------------------------------------------------------------------------
def test_opportunity_confidence_high():
    result = analyze(
        signal_types=[
            SignalType.PROJECT_AWARD,
            SignalType.HIRING,
            SignalType.DIGITAL_TRANSFORMATION,
        ],
        estimated_hiring=45,
        detected_technologies=["Java", "AWS", "DevOps"],
        signal_strength=100,
    )
    assert result.opportunity_confidence >= 80
    assert result.opportunity_confidence_label == "HIGH"


def test_opportunity_confidence_bounds():
    result = analyze(
        signal_types=list(SignalType),
        estimated_hiring=10_000,
        detected_technologies=["Java"] * 20,
        signal_strength=100,
    )
    assert 0 <= result.opportunity_confidence <= 100


# 17 ------------------------------------------------------------------------
def test_missing_optional_fields():
    # No lead_data at all; analyzer must not error.
    result = analyzer.analyze(None, _sig(signal_types=[SignalType.HIRING], estimated_hiring=3))
    assert isinstance(result, OpportunityAssessment)
    assert result.opportunity_type is OpportunityType.NORMAL_HIRING


# 18 ------------------------------------------------------------------------
def test_weak_ambiguous_signals():
    result = analyze(signal_types=[SignalType.OTHER], signal_strength=5)
    assert result.opportunity_type is OpportunityType.LOW_CONFIDENCE


# 19 ------------------------------------------------------------------------
def test_multiple_signals_populate_secondary():
    result = analyze(
        signal_types=[SignalType.PROJECT_AWARD, SignalType.HIRING, SignalType.DIGITAL_TRANSFORMATION],
        estimated_hiring=45,
        detected_technologies=["Java", "AWS"],
        signal_strength=100,
    )
    assert result.opportunity_type is OpportunityType.LARGE_SCALE_RAMP_UP
    assert len(result.secondary_opportunity_types) >= 1


# 20 ------------------------------------------------------------------------
def test_no_it_related_signal():
    result = analyze(signal_types=[SignalType.OTHER], signal_strength=0)
    assert result.opportunity_type is OpportunityType.LOW_CONFIDENCE
    assert result.likely_technologies == []
    assert result.likely_roles == []


# determinism + serialization ----------------------------------------------
def test_deterministic_output():
    a = analyze(signal_types=[SignalType.PROJECT_AWARD, SignalType.HIRING], estimated_hiring=30, signal_strength=90)
    b = analyze(signal_types=[SignalType.PROJECT_AWARD, SignalType.HIRING], estimated_hiring=30, signal_strength=90)
    assert a.model_dump() == b.model_dump()


def test_enums_serialize_to_strings():
    result = analyze(
        signal_types=[SignalType.PROJECT_AWARD, SignalType.HIRING],
        estimated_hiring=45,
        signal_strength=100,
    )
    payload = result.model_dump(mode="json")
    assert payload["opportunity_type"] == "LARGE_SCALE_RAMP_UP"
    assert payload["potential_staffing_need"] in {s.value for s in StaffingNeed}
    assert payload["urgency"] in {u.value for u in Urgency}


# §15 integration: SignalDetector -> OpportunityAnalyzer --------------------
def test_integration_signal_detector_to_analyzer():
    text = (
        "Company won a major banking transformation project and is hiring "
        "30 Java engineers, 10 AWS engineers and 5 DevOps specialists."
    )
    detection = SignalDetector().detect(signal_description=text)
    result = run_opportunity_analysis({"signal_description": text}, detection)

    assert result.opportunity_type is OpportunityType.LARGE_SCALE_RAMP_UP
    assert result.potential_staffing_need is StaffingNeed.HIGH
    assert {"Java", "AWS", "DevOps"}.issubset(set(result.likely_technologies))
    assert result.estimated_team_size_min == 45 and result.estimated_team_size_max == 45
    assert result.urgency in {Urgency.HIGH, Urgency.CRITICAL}
    assert result.opportunity_confidence_label == "HIGH"


# §13 scenarios -------------------------------------------------------------
def test_scenario_2_single_frontend_developer():
    detection = SignalDetector().detect(signal_description="Company is hiring one frontend developer.")
    result = run_opportunity_analysis({"signal_description": "Company is hiring one frontend developer."}, detection)
    assert result.opportunity_type is OpportunityType.NORMAL_HIRING
    assert result.potential_staffing_need is StaffingNeed.LOW
    assert result.urgency in {Urgency.LOW, Urgency.MEDIUM}


def test_scenario_3_implementation_partner():
    text = "Company is seeking an implementation partner for its cloud modernization initiative."
    detection = SignalDetector().detect(signal_description=text)
    result = run_opportunity_analysis({"signal_description": text}, detection)
    assert result.opportunity_type in {
        OpportunityType.VENDOR_OPPORTUNITY,
        OpportunityType.TECHNOLOGY_IMPLEMENTATION,
    }
    assert result.potential_staffing_need in {StaffingNeed.MEDIUM, StaffingNeed.HIGH}


def test_scenario_4_administrative_vacancy():
    text = "Company posted a general office administrator vacancy."
    detection = SignalDetector().detect(signal_description=text)
    result = run_opportunity_analysis({"signal_description": text}, detection)
    assert result.opportunity_type is OpportunityType.LOW_CONFIDENCE
    assert result.potential_staffing_need is StaffingNeed.LOW
