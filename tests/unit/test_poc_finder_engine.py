"""Unit tests for the POCFinder role-recommendation engine."""

from database.models import SignalType
from enrichment.poc_finder import (
    DecisionMakerType,
    POCFinder,
    POCFinderConfig,
    POCRecommendationResult,
    RoleCategory,
    RoleRecommendation,
    run_poc_recommendation,
)
from intelligence.opportunity_analyzer import (
    OpportunityAnalyzer,
    OpportunityAssessment,
    OpportunityType,
)
from intelligence.signal_detector import SignalDetectionResult, SignalDetector

finder = POCFinder()


def _sig(**kwargs) -> SignalDetectionResult:
    defaults = dict(
        signal_types=[SignalType.HIRING],
        signal_strength=60,
        signal_strength_label="MEDIUM",
        detected_technologies=[],
        detected_roles=[],
        estimated_hiring=None,
        project_value=None,
    )
    defaults.update(kwargs)
    return SignalDetectionResult(**defaults)


def _opp(opp_type: OpportunityType, confidence: int = 80) -> OpportunityAssessment:
    return OpportunityAssessment(opportunity_type=opp_type, opportunity_confidence=confidence)


def recommend(lead=None, opp=None, **sig_kwargs) -> POCRecommendationResult:
    return finder.recommend(lead or {}, _sig(**sig_kwargs), opp)


def _all_roles(result: POCRecommendationResult) -> set[str]:
    roles = {result.primary_role.role} if result.primary_role else set()
    return roles | {r.role for r in result.secondary_roles}


# 1-8 signal-to-role --------------------------------------------------------
def test_hiring_maps_to_engineering_leadership():
    result = recommend(signal_types=[SignalType.HIRING])
    assert result.primary_role.role_category in {
        RoleCategory.ENGINEERING_LEADERSHIP,
        RoleCategory.TECHNOLOGY_LEADERSHIP,
    }


def test_large_technology_hiring():
    result = recommend(signal_types=[SignalType.HIRING], estimated_hiring=45)
    assert result.primary_role.role in {"VP Engineering", "CTO", "Head of Engineering", "Engineering Director"}


def test_project_award():
    result = recommend(signal_types=[SignalType.PROJECT_AWARD])
    assert "CTO" in _all_roles(result) or "CIO" in _all_roles(result)


def test_project_execution():
    result = recommend(signal_types=[SignalType.PROJECT_EXECUTION])
    assert result.primary_role.decision_maker_type in {DecisionMakerType.DELIVERY, DecisionMakerType.TECHNICAL}
    assert "Delivery Head" in _all_roles(result)


def test_digital_transformation():
    result = recommend(signal_types=[SignalType.DIGITAL_TRANSFORMATION])
    assert _all_roles(result) & {"CIO", "CTO", "Chief Digital Officer", "Transformation Director"}


def test_technology_initiative():
    result = recommend(signal_types=[SignalType.TECHNOLOGY_INITIATIVE])
    assert _all_roles(result) & {"CTO", "CIO", "VP Engineering", "Head of Technology"}


def test_vendor_requirement():
    result = recommend(signal_types=[SignalType.VENDOR_REQUIREMENT])
    assert result.primary_role.role in {"Vendor Manager", "IT Sourcing Manager", "Procurement Head"}
    assert result.primary_role.decision_maker_type in {DecisionMakerType.VENDOR, DecisionMakerType.PROCUREMENT}


def test_contract():
    result = recommend(signal_types=[SignalType.CONTRACT])
    assert _all_roles(result) & {"Procurement Head", "Vendor Manager", "IT Sourcing Manager"}


# 9-12 opportunity-to-role --------------------------------------------------
def test_staff_augmentation():
    result = recommend(opp=_opp(OpportunityType.STAFF_AUGMENTATION), signal_types=[SignalType.PROJECT_EXECUTION])
    assert result.primary_role.role in {"VP Engineering", "Head of Engineering", "Engineering Director"}


def test_vendor_opportunity():
    result = recommend(
        {"industry": "IT"},
        opp=_opp(OpportunityType.VENDOR_OPPORTUNITY),
        signal_types=[SignalType.VENDOR_REQUIREMENT],
        signal_strength=80,
    )
    assert result.primary_role.role in {"Vendor Manager", "IT Sourcing Manager"}
    assert result.recommendation_confidence_label == "HIGH"


def test_large_scale_ramp_up():
    result = recommend(
        {"industry": "BFSI"},
        opp=_opp(OpportunityType.LARGE_SCALE_RAMP_UP),
        signal_types=[SignalType.PROJECT_AWARD, SignalType.HIRING, SignalType.DIGITAL_TRANSFORMATION],
        estimated_hiring=45,
        signal_strength=100,
    )
    assert result.primary_role.role in {"VP Engineering", "CTO"}
    assert _all_roles(result) & {"Delivery Head", "Program Director", "Vendor Manager"}


def test_technology_implementation():
    result = recommend(opp=_opp(OpportunityType.TECHNOLOGY_IMPLEMENTATION), signal_types=[SignalType.TECHNOLOGY_INITIATIVE])
    assert _all_roles(result) & {"CTO", "CIO", "Program Director", "Delivery Head"}


# 13-16 industries ----------------------------------------------------------
def test_bfsi_industry():
    result = recommend({"industry": "BFSI"}, signal_types=[SignalType.PROJECT_AWARD])
    assert _all_roles(result) & {"CIO", "CTO", "Technology Delivery Head", "IT Procurement Head", "Program Director"}


def test_it_industry():
    result = recommend({"industry": "IT Services"}, signal_types=[SignalType.HIRING])
    assert _all_roles(result) & {"CTO", "VP Engineering", "Engineering Director", "Delivery Head"}


def test_fmcg_industry():
    result = recommend({"industry": "FMCG"}, signal_types=[SignalType.DIGITAL_TRANSFORMATION])
    assert _all_roles(result) & {"CIO", "CTO", "Digital Transformation Head", "IT Procurement Head"}


def test_healthcare_industry():
    result = recommend({"industry": "Healthcare"}, signal_types=[SignalType.DIGITAL_TRANSFORMATION])
    assert _all_roles(result) & {"CIO", "CTO", "Digital Transformation Head", "Technology Delivery Head"}


# 17-20 selection / scoring / type ------------------------------------------
def test_primary_role_selection_is_highest_relevance():
    result = recommend(
        opp=_opp(OpportunityType.LARGE_SCALE_RAMP_UP),
        signal_types=[SignalType.PROJECT_AWARD, SignalType.HIRING],
        estimated_hiring=40,
    )
    assert result.primary_role is not None
    assert all(result.primary_role.relevance_score >= r.relevance_score for r in result.secondary_roles)


def test_secondary_roles_present():
    result = recommend(
        opp=_opp(OpportunityType.LARGE_SCALE_RAMP_UP),
        signal_types=[SignalType.PROJECT_AWARD, SignalType.HIRING],
        estimated_hiring=45,
    )
    assert len(result.secondary_roles) >= 1


def test_role_relevance_score_in_range():
    result = recommend(signal_types=[SignalType.PROJECT_AWARD, SignalType.HIRING], estimated_hiring=45)
    for r in [result.primary_role, *result.secondary_roles]:
        assert 0 <= r.relevance_score <= 100
        assert r.reason


def test_decision_maker_type_assigned():
    result = recommend(signal_types=[SignalType.VENDOR_REQUIREMENT])
    assert isinstance(result.primary_role.decision_maker_type, DecisionMakerType)


# 21 confidence -------------------------------------------------------------
def test_recommendation_confidence_high():
    result = recommend(
        {"industry": "BFSI"},
        opp=_opp(OpportunityType.LARGE_SCALE_RAMP_UP),
        signal_types=[SignalType.PROJECT_AWARD, SignalType.HIRING, SignalType.DIGITAL_TRANSFORMATION],
        estimated_hiring=45,
        signal_strength=100,
    )
    assert result.recommendation_confidence >= 80
    assert result.recommendation_confidence_label == "HIGH"


# 22 no useful signal -------------------------------------------------------
def test_no_useful_signal():
    result = recommend(signal_types=[SignalType.OTHER], signal_strength=0)
    assert result.primary_role is None
    assert result.secondary_roles == []
    assert result.recommendation_confidence_label == "LOW"


# 23 deduplication ----------------------------------------------------------
def test_no_duplicate_roles():
    result = recommend(
        opp=_opp(OpportunityType.LARGE_SCALE_RAMP_UP),
        signal_types=[SignalType.PROJECT_AWARD, SignalType.HIRING, SignalType.DIGITAL_TRANSFORMATION],
        estimated_hiring=45,
    )
    all_roles = ([result.primary_role.role] if result.primary_role else []) + [r.role for r in result.secondary_roles]
    assert len(all_roles) == len(set(all_roles))


def test_sorted_by_relevance_descending():
    result = recommend(
        opp=_opp(OpportunityType.LARGE_SCALE_RAMP_UP),
        signal_types=[SignalType.PROJECT_AWARD, SignalType.HIRING],
        estimated_hiring=45,
    )
    scores = [r.relevance_score for r in result.secondary_roles]
    assert scores == sorted(scores, reverse=True)


# 24 determinism ------------------------------------------------------------
def test_deterministic_repeated_execution():
    args = dict(
        opp=_opp(OpportunityType.LARGE_SCALE_RAMP_UP),
        signal_types=[SignalType.PROJECT_AWARD, SignalType.HIRING],
        estimated_hiring=30,
    )
    assert recommend(**args).model_dump() == recommend(**args).model_dump()


# extra: scenarios 3 & 4, config, serialization, wrapper --------------------
def test_scenario_single_frontend_developer_not_procurement():
    detection = SignalDetector().detect(signal_description="Company is hiring one frontend developer.")
    opportunity = OpportunityAnalyzer().analyze({"signal_description": "one frontend developer"}, detection)
    result = finder.recommend({}, detection, opportunity)
    assert result.primary_role is not None
    assert result.primary_role.decision_maker_type is not DecisionMakerType.PROCUREMENT
    assert result.primary_role.role in {"Engineering Manager", "Engineering Director", "VP Engineering"}


def test_scenario_office_administrator_no_recommendation():
    detection = SignalDetector().detect(signal_description="General office administrator hiring.")
    opportunity = OpportunityAnalyzer().analyze({}, detection)
    result = finder.recommend({}, detection, opportunity)
    assert result.recommendation_confidence_label == "LOW"


def test_configurable_industry_map():
    custom = POCFinderConfig(industry_roles={"IT": ["Head of Technology"]})
    result = POCFinder(custom).recommend({"industry": "IT"}, _sig(signal_types=[SignalType.HIRING]))
    assert "Head of Technology" in _all_roles(result)


def test_enums_serialize_to_strings():
    result = recommend(signal_types=[SignalType.VENDOR_REQUIREMENT])
    payload = result.model_dump(mode="json")
    assert payload["primary_role"]["decision_maker_type"] in {t.value for t in DecisionMakerType}
    assert payload["primary_role"]["role_category"] in {c.value for c in RoleCategory}


def test_convenience_wrapper():
    result = run_poc_recommendation({}, _sig(signal_types=[SignalType.HIRING]))
    assert isinstance(result, POCRecommendationResult)


# 19 integration: detector -> analyzer -> poc finder ------------------------
def test_integration_pipeline():
    text = (
        "Company won a major banking transformation project and is hiring "
        "30 Java engineers, 10 AWS engineers and 5 DevOps specialists."
    )
    lead = {"company_name": "NorthStar", "industry": "BFSI", "signal_description": text}
    signal = SignalDetector().detect(signal_description=text)
    opportunity = OpportunityAnalyzer().analyze(lead, signal)
    result = finder.recommend(lead, signal, opportunity)

    assert signal.signal_types
    assert opportunity.opportunity_type
    assert result.primary_role is not None
    assert result.secondary_roles
    assert 0 <= result.primary_role.relevance_score <= 100
    assert result.recommendation_confidence_label in {"MEDIUM", "HIGH"}
