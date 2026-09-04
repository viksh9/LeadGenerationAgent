"""Repository CRUD tests against an isolated database."""

from database.models import LeadPriority, LeadStatus
from database.repository import create_lead, delete_lead, get_lead, list_leads, update_lead


def test_create_returns_persisted_lead(db_session, sample_lead_data):
    lead = create_lead(db_session, **sample_lead_data)
    assert lead.id is not None
    assert lead.status == LeadStatus.NEW
    assert lead.lead_priority == LeadPriority.HOT


def test_get_returns_lead(db_session, sample_lead_data):
    created = create_lead(db_session, **sample_lead_data)
    fetched = get_lead(db_session, created.id)
    assert fetched is not None
    assert fetched.id == created.id
    assert fetched.company_name == "NorthStar Banking Technologies"


def test_list_returns_and_filters_leads(db_session):
    create_lead(db_session, company_name="Alpha", lead_score=90.0, status=LeadStatus.NEW)
    create_lead(db_session, company_name="Beta", lead_score=40.0, status=LeadStatus.QUALIFIED)
    create_lead(db_session, company_name="Gamma", lead_score=10.0, status=LeadStatus.NEW)

    assert len(list_leads(db_session)) == 3
    assert len(list_leads(db_session, status=LeadStatus.NEW)) == 2
    assert len(list_leads(db_session, min_score=50.0)) == 1

    limited = list_leads(db_session, limit=2)
    assert len(limited) == 2


def test_update_changes_fields(db_session, sample_lead_data):
    created = create_lead(db_session, **sample_lead_data)
    updated = update_lead(
        db_session,
        created.id,
        status=LeadStatus.CONTACTED,
        lead_priority=LeadPriority.WARM,
        lead_score=88.0,
    )
    assert updated is not None
    assert updated.status == LeadStatus.CONTACTED
    assert updated.lead_priority == LeadPriority.WARM
    assert updated.lead_score == 88.0


def test_delete_removes_lead(db_session, sample_lead_data):
    created = create_lead(db_session, **sample_lead_data)
    assert delete_lead(db_session, created.id) is True
    assert get_lead(db_session, created.id) is None


def test_missing_lead_behaviour(db_session):
    assert get_lead(db_session, 999999) is None
    assert update_lead(db_session, 999999, lead_score=10.0) is None
    assert delete_lead(db_session, 999999) is False
