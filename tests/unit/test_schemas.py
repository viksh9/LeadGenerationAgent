"""Validation tests for the API schema layer."""

import pytest
from pydantic import ValidationError

from api.schemas import (
    LeadAnalyzeRequest,
    LeadAnalyzeResponse,
    LeadCreate,
    LeadListResponse,
    LeadResponse,
    LeadUpdate,
    OpportunityAnalysis,
    ScoreComponent,
)
from database.models import LeadPriority, LeadStatus, SignalType
from database.repository import create_lead

CALCULATED_FIELDS = [
    "lead_score",
    "lead_priority",
    "opportunity_summary",
    "recommended_action",
    "recommended_pitch",
]


# 1 --------------------------------------------------------------------------
def test_valid_lead_create():
    lead = LeadCreate(
        company_name="NorthStar Banking Technologies",
        industry="BFSI",
        signal_type=SignalType.DIGITAL_TRANSFORMATION,
        source_url="https://news.example/story",
        company_website="https://northstar-banking.example",
        poc_linkedin_url="https://linkedin.com/in/anita-desai",
        technologies=["Java", "AWS"],
        estimated_hiring=40,
        project_value=2_500_000.0,
        signal_confidence=90.0,
    )
    assert lead.company_name == "NorthStar Banking Technologies"
    assert lead.signal_type is SignalType.DIGITAL_TRANSFORMATION
    assert lead.status is LeadStatus.NEW  # default


# 2 --------------------------------------------------------------------------
def test_empty_company_name_rejected():
    with pytest.raises(ValidationError):
        LeadCreate(company_name="")


# 3 --------------------------------------------------------------------------
def test_whitespace_company_name_rejected():
    with pytest.raises(ValidationError):
        LeadCreate(company_name="    ")


def test_company_name_is_trimmed():
    assert LeadCreate(company_name="  Acme  ").company_name == "Acme"


# 4 --------------------------------------------------------------------------
def test_invalid_source_url_rejected():
    with pytest.raises(ValidationError):
        LeadCreate(company_name="Acme", source_url="not-a-url")


# 5 --------------------------------------------------------------------------
def test_invalid_company_website_rejected():
    with pytest.raises(ValidationError):
        LeadCreate(company_name="Acme", company_website="also-not-a-url")


# 6 --------------------------------------------------------------------------
def test_invalid_linkedin_url_rejected():
    with pytest.raises(ValidationError):
        LeadCreate(company_name="Acme", poc_linkedin_url="nope")


def test_empty_url_string_is_treated_as_none():
    lead = LeadCreate(company_name="Acme", source_url="   ")
    assert lead.source_url is None


# 7 --------------------------------------------------------------------------
def test_negative_estimated_hiring_rejected():
    with pytest.raises(ValidationError):
        LeadCreate(company_name="Acme", estimated_hiring=-1)


# 8 --------------------------------------------------------------------------
def test_negative_project_value_rejected():
    with pytest.raises(ValidationError):
        LeadCreate(company_name="Acme", project_value=-0.01)


# 9 --------------------------------------------------------------------------
def test_signal_confidence_below_zero_rejected():
    with pytest.raises(ValidationError):
        LeadCreate(company_name="Acme", signal_confidence=-1)


# 10 -------------------------------------------------------------------------
def test_signal_confidence_above_hundred_rejected():
    with pytest.raises(ValidationError):
        LeadCreate(company_name="Acme", signal_confidence=100.1)


# 11 -------------------------------------------------------------------------
def test_valid_lead_update():
    upd = LeadUpdate(
        company_name="Acme Renamed",
        status=LeadStatus.CONTACTED,
        estimated_hiring=5,
        source_url="https://acme.example/news",
    )
    assert upd.company_name == "Acme Renamed"
    assert upd.status is LeadStatus.CONTACTED


# 12 -------------------------------------------------------------------------
def test_partial_lead_update_only_sets_provided_fields():
    upd = LeadUpdate(status=LeadStatus.QUALIFIED)
    dumped = upd.model_dump(exclude_unset=True)
    assert dumped == {"status": LeadStatus.QUALIFIED}


def test_lead_update_empty_company_name_rejected():
    with pytest.raises(ValidationError):
        LeadUpdate(company_name="   ")


# 13 -------------------------------------------------------------------------
def test_lead_response_orm_compatibility(db_session, sample_lead_data):
    lead = create_lead(db_session, **sample_lead_data)
    resp = LeadResponse.model_validate(lead)
    assert resp.id == lead.id
    assert resp.company_name == "NorthStar Banking Technologies"
    assert resp.signal_type is SignalType.DIGITAL_TRANSFORMATION
    assert resp.lead_priority is LeadPriority.HOT
    assert resp.technologies == ["Java", "Spring Boot", "AWS", "DevOps"]
    # Enums + timestamps serialize to clean, frontend-friendly JSON.
    payload = resp.model_dump(mode="json")
    assert payload["lead_priority"] == "HOT"
    assert payload["signal_type"] == "DIGITAL_TRANSFORMATION"
    assert payload["status"] == "NEW"
    assert isinstance(payload["created_at"], str) and "T" in payload["created_at"]


def test_lead_list_response_shape():
    lst = LeadListResponse(items=[LeadResponse(id=1, company_name="Acme")], total=1)
    payload = lst.model_dump(mode="json")
    assert payload["total"] == 1
    assert payload["items"][0]["company_name"] == "Acme"


# 14 -------------------------------------------------------------------------
def test_lead_analyze_request():
    req = LeadAnalyzeRequest(
        company_name="NorthStar Banking Technologies",
        signal_title="Digital banking transformation + hiring",
        technologies=["Java", "AWS"],
        estimated_hiring=40,
        signal_confidence=88.0,
        source_url="https://news.example/story",
    )
    assert req.company_name == "NorthStar Banking Technologies"
    # Calculated fields are not part of the request contract.
    assert not hasattr(req, "lead_score")


def test_lead_analyze_request_ignores_unknown_extras():
    req = LeadAnalyzeRequest(company_name="Acme", lead_score=999)
    assert not hasattr(req, "lead_score")


def test_lead_analyze_request_requires_company_name():
    with pytest.raises(ValidationError):
        LeadAnalyzeRequest(company_name="  ")


# 15 -------------------------------------------------------------------------
def test_lead_analyze_response():
    resp = LeadAnalyzeResponse(
        lead=LeadResponse(id=7, company_name="NorthStar Banking Technologies"),
        opportunity_analysis=OpportunityAnalysis(
            summary="Greenfield digital banking build with active hiring.",
            recommended_motion="Architecture discovery call",
            pain_hypotheses=["Legacy core blocking integrations."],
        ),
        score=82.0,
        priority=LeadPriority.HOT,
        score_breakdown=[
            ScoreComponent(label="signal_strength", points=50.0),
            ScoreComponent(label="hiring_volume", points=32.0),
        ],
        recommended_action="Book a platform architecture discovery call.",
    )
    payload = resp.model_dump(mode="json")
    assert payload["priority"] == "HOT"
    assert payload["lead"]["company_name"] == "NorthStar Banking Technologies"
    assert payload["score_breakdown"][0]["label"] == "signal_strength"


# API safety ----------------------------------------------------------------
@pytest.mark.parametrize("field", CALCULATED_FIELDS)
def test_lead_create_forbids_calculated_fields(field):
    with pytest.raises(ValidationError):
        LeadCreate(**{"company_name": "Acme", field: "x"})


@pytest.mark.parametrize("field", CALCULATED_FIELDS)
def test_lead_update_forbids_calculated_fields(field):
    with pytest.raises(ValidationError):
        LeadUpdate(**{field: "x"})
