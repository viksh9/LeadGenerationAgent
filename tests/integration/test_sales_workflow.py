"""Sales workflow additions (Prompt 56): disqualification-reason enforcement (§14) and
the manual follow-up create endpoint (§9/§24). Throwaway DB via the `client` fixture."""

from __future__ import annotations

import api.main
from api.dependencies import get_session
from database.models import (
    DataProvenance,
    FollowUpStatus,
    FollowUpTask,
    Lead,
    LeadPriority,
    LeadStatus,
    SignalType,
)


def _seed(client) -> int:
    session = next(api.main.app.dependency_overrides[get_session]())
    lead = Lead(company_name="Infosys Ltd", normalized_company_name="infosys ltd", lead_score=85,
                lead_priority=LeadPriority.HOT, status=LeadStatus.NEW, signal_type=SignalType.HIRING,
                estimated_hiring=30, data_provenance=DataProvenance.REAL)
    session.add(lead)
    session.commit()
    lead_id = lead.id
    session.close()
    return lead_id


# --- Disqualification requires a reason (§14) ------------------------------- #
def test_disqualify_without_reason_rejected(client):
    lead_id = _seed(client)
    r = client.post(f"/leads/{lead_id}/transition", json={"new_status": "DISQUALIFIED"})
    assert r.status_code == 422
    assert "reason" in r.json()["error"]["message"].lower()
    # Status unchanged.
    session = next(api.main.app.dependency_overrides[get_session]())
    assert session.get(Lead, lead_id).status == LeadStatus.NEW


def test_disqualify_with_reason_persists_reason(client):
    lead_id = _seed(client)
    r = client.post(f"/leads/{lead_id}/transition",
                    json={"new_status": "DISQUALIFIED", "reason": "Wrong geography"})
    assert r.status_code == 200 and r.json()["new_status"] == "DISQUALIFIED"
    assert r.json()["reason"] == "Wrong geography"          # reason stored in history


def test_illegal_transition_rejected(client):
    lead_id = _seed(client)
    # NEW -> WON is not an allowed transition.
    r = client.post(f"/leads/{lead_id}/transition", json={"new_status": "WON"})
    assert r.status_code == 422


# --- Manual follow-up create (§9/§24) --------------------------------------- #
def test_create_follow_up_for_lead(client):
    lead_id = _seed(client)
    r = client.post(f"/leads/{lead_id}/follow-ups",
                    json={"title": "Call next Tuesday", "reason": "reviewed hiring"})
    assert r.status_code == 200
    body = r.json()
    assert body["title"] == "Call next Tuesday" and body["lead_id"] == lead_id
    assert body["status"] == "OPEN" and body["task_type"] == "FOLLOW_UP"
    # Appears in the lead's follow-up queue.
    q = client.get(f"/follow-ups?lead_id={lead_id}").json()
    assert any(t["id"] == body["id"] for t in q["items"])


def test_create_follow_up_missing_title_rejected(client):
    lead_id = _seed(client)
    assert client.post(f"/leads/{lead_id}/follow-ups", json={}).status_code == 422


def test_create_follow_up_unknown_lead_404(client):
    assert client.post("/leads/999999/follow-ups", json={"title": "x"}).status_code == 404


def test_follow_up_uses_canonical_lead_id_no_duplicate_leads(client):
    lead_id = _seed(client)
    client.post(f"/leads/{lead_id}/follow-ups", json={"title": "t1"})
    client.post(f"/leads/{lead_id}/follow-ups", json={"title": "t2"})
    session = next(api.main.app.dependency_overrides[get_session]())
    assert session.query(Lead).count() == 1                 # no lead duplication
    assert session.query(FollowUpTask).filter(FollowUpTask.lead_id == lead_id).count() == 2
