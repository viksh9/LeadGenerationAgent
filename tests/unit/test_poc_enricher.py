"""Unit tests for the POCEnricher engine."""

from database.models import SignalType
from enrichment.poc_finder import (
    ContactPriority,
    Department,
    POCEnricher,
    POCEnrichmentResult,
    Seniority,
    run_poc_enrichment,
)
from intelligence.opportunity_analyzer import (
    OpportunityAnalyzer,
    OpportunityAssessment,
    OpportunityType,
)
from intelligence.signal_detector import SignalDetectionResult, SignalDetector

enricher = POCEnricher()


def _opp(opp_type: OpportunityType, confidence: int = 70) -> OpportunityAssessment:
    return OpportunityAssessment(opportunity_type=opp_type, opportunity_confidence=confidence)


def enrich(lead_data=None, opp_type=OpportunityType.PROJECT_DRIVEN_HIRING, confidence=70):
    return enricher.enrich(lead_data, None, _opp(opp_type, confidence))


# personas per opportunity type ---------------------------------------------
def test_vendor_opportunity_targets_procurement_and_technology():
    result = enrich(opp_type=OpportunityType.VENDOR_OPPORTUNITY)
    depts = {c.department for c in result.recommended_contacts}
    assert Department.PROCUREMENT in depts
    assert Department.TECHNOLOGY in depts
    assert result.primary_contact is not None
    assert result.primary_contact.is_decision_maker


def test_ramp_up_targets_engineering_and_delivery():
    result = enrich(opp_type=OpportunityType.LARGE_SCALE_RAMP_UP)
    depts = {c.department for c in result.recommended_contacts}
    assert Department.ENGINEERING in depts
    assert Department.DELIVERY in depts
    assert Department.ENGINEERING in result.target_departments or Department.DELIVERY in result.target_departments


def test_normal_hiring_targets_engineering_manager():
    result = enrich(opp_type=OpportunityType.NORMAL_HIRING)
    titles = {c.title for c in result.recommended_contacts}
    assert "Engineering Manager" in titles


def test_digital_transformation_targets_cxo():
    result = enrich(opp_type=OpportunityType.DIGITAL_TRANSFORMATION)
    seniorities = {c.seniority for c in result.recommended_contacts}
    assert Seniority.C_LEVEL in seniorities


def test_low_confidence_opportunity_is_minimal():
    result = enrich(opp_type=OpportunityType.LOW_CONFIDENCE, confidence=0)
    assert result.enrichment_confidence_label == "LOW"
    assert "gather more information" in result.outreach_focus.lower()


# recommendations never fabricate people ------------------------------------
def test_recommended_contacts_are_personas_not_people():
    result = enrich(opp_type=OpportunityType.LARGE_SCALE_RAMP_UP)
    # Personas carry a role title but no personal name field.
    assert all(hasattr(c, "title") and not hasattr(c, "full_name") for c in result.recommended_contacts)


def test_no_known_contacts_when_none_supplied():
    result = enrich(opp_type=OpportunityType.VENDOR_OPPORTUNITY)
    assert result.ranked_known_contacts == []
    assert result.best_known_contact is None


# known contact ranking -----------------------------------------------------
def test_known_contacts_ranked_by_seniority():
    lead = {
        "company_website": "https://northstar-banking.example",
        "contacts": [
            {"full_name": "Sam Lee", "title": "Engineering Manager"},
            {"full_name": "Priya Raman", "title": "VP of Engineering"},
            {"full_name": "Alex Doe", "title": "Software Engineer"},
        ],
    }
    result = enricher.enrich(lead, None, _opp(OpportunityType.PROJECT_DRIVEN_HIRING))
    assert result.best_known_contact.full_name == "Priya Raman"
    assert result.best_known_contact.is_decision_maker is True
    assert result.best_known_contact.seniority is Seniority.VP


def test_known_contact_email_pattern_suggested():
    lead = {
        "company_website": "https://northstar-banking.example",
        "contacts": [{"full_name": "Priya Raman", "title": "VP of Engineering"}],
    }
    result = enricher.enrich(lead, None, _opp(OpportunityType.PROJECT_DRIVEN_HIRING))
    assert result.best_known_contact.suggested_email == "priya.raman@northstar-banking.example"


def test_existing_email_is_preserved():
    lead = {"contacts": [{"full_name": "Priya Raman", "title": "VP", "email": "p@corp.example"}]}
    result = enricher.enrich(lead, None, _opp(OpportunityType.PROJECT_DRIVEN_HIRING))
    assert result.best_known_contact.email == "p@corp.example"
    assert result.best_known_contact.suggested_email == "p@corp.example"


def test_flat_lead_poc_fields_are_used():
    lead = {
        "poc_name": "Dana Fox",
        "poc_title": "Head of Delivery",
        "company_website": "acme.example",
    }
    result = enricher.enrich(lead, None, _opp(OpportunityType.PROJECT_DRIVEN_HIRING))
    assert result.best_known_contact.full_name == "Dana Fox"
    assert result.best_known_contact.is_decision_maker is True
    assert result.best_known_contact.suggested_email == "dana.fox@acme.example"


# targets + confidence ------------------------------------------------------
def test_target_departments_and_seniority():
    result = enrich(opp_type=OpportunityType.VENDOR_OPPORTUNITY)
    assert result.target_departments  # non-empty
    assert result.target_seniority in set(Seniority)


def test_confidence_increases_with_known_decision_maker():
    base = enrich(opp_type=OpportunityType.PROJECT_DRIVEN_HIRING, confidence=70)
    with_dm = enricher.enrich(
        {"contacts": [{"full_name": "Priya Raman", "title": "VP of Engineering"}]},
        None,
        _opp(OpportunityType.PROJECT_DRIVEN_HIRING, 70),
    )
    assert with_dm.enrichment_confidence > base.enrichment_confidence


def test_confidence_bounds():
    result = enrich(opp_type=OpportunityType.LARGE_SCALE_RAMP_UP, confidence=100)
    assert 0 <= result.enrichment_confidence <= 100


# robustness ----------------------------------------------------------------
def test_missing_optional_fields_no_opportunity():
    result = enricher.enrich(None, None, None)
    assert isinstance(result, POCEnrichmentResult)
    assert result.recommended_contacts  # falls back to a minimal persona
    assert result.enrichment_confidence_label == "LOW"


def test_deterministic_output():
    a = enrich(opp_type=OpportunityType.VENDOR_OPPORTUNITY)
    b = enrich(opp_type=OpportunityType.VENDOR_OPPORTUNITY)
    assert a.model_dump() == b.model_dump()


def test_enums_serialize_to_strings():
    result = enrich(opp_type=OpportunityType.VENDOR_OPPORTUNITY)
    payload = result.model_dump(mode="json")
    assert payload["primary_contact"]["department"] in {d.value for d in Department}
    assert payload["target_seniority"] in {s.value for s in Seniority}
    assert payload["primary_contact"]["priority"] in {p.value for p in ContactPriority}


# integration: detector -> analyzer -> enricher -----------------------------
def test_integration_pipeline():
    text = (
        "Company won a major banking transformation project and is hiring "
        "30 Java engineers, 10 AWS engineers and 5 DevOps specialists."
    )
    detection = SignalDetector().detect(signal_description=text)
    opportunity = OpportunityAnalyzer().analyze({"signal_description": text}, detection)
    result = run_poc_enrichment(
        {"signal_description": text, "company_website": "https://northstar-banking.example"},
        detection,
        opportunity,
    )
    # Ramp-up should target engineering/delivery leadership.
    depts = {c.department for c in result.recommended_contacts}
    assert depts & {Department.ENGINEERING, Department.DELIVERY}
    assert result.primary_contact.is_decision_maker
    assert result.enrichment_confidence_label in {"MEDIUM", "HIGH"}
