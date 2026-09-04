"""Model-level tests: fields, defaults, enums, and constraints."""

import pytest

from config.exceptions import ValidationError
from database.models import Lead, LeadPriority, LeadStatus, SignalType
from database.repository import create_lead


def test_lead_model_creation(db_session, sample_lead_data):
    lead = create_lead(db_session, **sample_lead_data)
    assert lead.id is not None
    assert lead.company_name == "NorthStar Banking Technologies"
    assert lead.industry == "BFSI"
    assert lead.signal_type == SignalType.DIGITAL_TRANSFORMATION
    assert lead.technologies == ["Java", "Spring Boot", "AWS", "DevOps"]
    assert lead.estimated_hiring == 40
    assert lead.created_at is not None
    assert lead.updated_at is not None


def test_company_name_is_required(db_session):
    with pytest.raises(ValidationError):
        create_lead(db_session, industry="BFSI")
    with pytest.raises(ValidationError):
        create_lead(db_session, company_name="   ")


def test_default_status_and_priority(db_session):
    lead = create_lead(db_session, company_name="Acme Corp")
    assert lead.status == LeadStatus.NEW
    assert lead.lead_priority == LeadPriority.LOW
    assert lead.lead_score == 0.0
    assert lead.technologies == []
    assert lead.hiring_roles == []


def test_lead_priority_values():
    assert {p.value for p in LeadPriority} == {"HOT", "WARM", "NURTURE", "LOW"}


def test_lead_priority_round_trips(db_session):
    lead = create_lead(db_session, company_name="Acme Corp", lead_priority=LeadPriority.HOT)
    fetched = db_session.get(Lead, lead.id)
    assert fetched.lead_priority == LeadPriority.HOT


@pytest.mark.parametrize("score", [0.0, 50.0, 100.0])
def test_lead_score_within_bounds_is_accepted(db_session, score):
    lead = create_lead(db_session, company_name="Acme Corp", lead_score=score)
    assert lead.lead_score == score


@pytest.mark.parametrize("score", [-1.0, 100.1, 150.0])
def test_lead_score_out_of_bounds_is_rejected(db_session, score):
    with pytest.raises(ValidationError):
        create_lead(db_session, company_name="Acme Corp", lead_score=score)


def test_estimated_hiring_cannot_be_negative(db_session):
    with pytest.raises(ValidationError):
        create_lead(db_session, company_name="Acme Corp", estimated_hiring=-5)
    ok = create_lead(db_session, company_name="Acme Corp", estimated_hiring=0)
    assert ok.estimated_hiring == 0


def test_signal_confidence_out_of_bounds_is_rejected(db_session):
    with pytest.raises(ValidationError):
        create_lead(db_session, company_name="Acme Corp", signal_confidence=120.0)
