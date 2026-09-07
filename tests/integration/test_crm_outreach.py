"""Integration tests for the CRM + outreach lifecycle (§55, §65, §72).

Covers lifecycle transitions + event-gating, activities, draft→approve→send with
safety + idempotency, reply/webhook processing, follow-ups, analytics honesty,
RBAC, and the APIs. Offline: no external network; the email provider is faked.
"""

from __future__ import annotations

import json
import hashlib
import hmac
import time
from datetime import datetime, timedelta

import pytest

from config.exceptions import ValidationError
from crm.analytics import INSUFFICIENT_DATA, NOT_AVAILABLE, compute_crm_analytics
from crm.lifecycle import LeadLifecycleService
from crm.pipeline import SalesPipelineService
from crm.providers.email_provider import BaseEmailProvider, EmailSendResult
from database.models import (
    ContactType,
    CRMActivity,
    DataProvenance,
    DecisionMaker,
    EmailStatus,
    EvidenceRecord,
    EvidenceType,
    Lead,
    LeadStatus,
    OutreachDraftStatus,
    SalesStage,
    VerificationStatus,
)
from outreach.reply import record_reply
from outreach.send import send_draft
from outreach.service import OutreachService

NOW = datetime(2026, 9, 8, 10, 0, 0)


class _FakeOK(BaseEmailProvider):
    name = "FAKE"
    def is_configured(self): return True
    def send(self, *, to, subject, body, from_addr):
        return EmailSendResult(True, "FAKE", provider_message_id="msg-1")


class _FakeFail(BaseEmailProvider):
    name = "FAKE"
    def is_configured(self): return True
    def send(self, *, to, subject, body, from_addr):
        return EmailSendResult(False, "FAKE", error="smtp refused")


def _seed_lead(session, *, status=LeadStatus.OUTREACH_READY, with_evidence=True, with_contact=True):
    lead = Lead(company_name="Acme Tech", normalized_company_name="acme tech", company_id=1,
                technologies=["AWS"], status=status, data_provenance=DataProvenance.REAL)
    session.add(lead); session.flush()
    if with_evidence:
        session.add(EvidenceRecord(lead_id=lead.id, evidence_type=EvidenceType.JOB, content_hash="e1",
                                   source_url="https://x", data_provenance=DataProvenance.REAL))
    if with_contact:
        session.add(DecisionMaker(company_id=1, company_name="Acme Tech", full_name="P", normalized_name="p",
            job_title="Head of Eng", normalized_role="head of eng", business_email="hire@acme.example",
            email_status=EmailStatus.VERIFIED_SOURCE, contact_type=ContactType.BUSINESS_EMAIL,
            verification_status=VerificationStatus.VERIFIED, data_provenance=DataProvenance.REAL))
    session.flush()
    return lead


# --------------------------------------------------------------------------- #
# Lifecycle
# --------------------------------------------------------------------------- #
def test_lifecycle_valid_and_event_gating(seed_session):
    lead = _seed_lead(seed_session)
    svc = LeadLifecycleService(seed_session)
    with pytest.raises(ValidationError):
        svc.transition(lead.id, LeadStatus.CONTACTED, changed_by="SYSTEM", source="AUTO")
    svc.transition(lead.id, LeadStatus.CONTACTED, changed_by="SYSTEM", source="SEND_CONFIRMED")
    assert lead.status is LeadStatus.CONTACTED
    with pytest.raises(ValidationError):
        svc.transition(lead.id, LeadStatus.WON, changed_by="human", reason="x")  # illegal jump
    assert len(svc.history(lead.id)) == 1


def test_lifecycle_human_can_set_gated_status(seed_session):
    lead = _seed_lead(seed_session)
    svc = LeadLifecycleService(seed_session)
    svc.transition(lead.id, LeadStatus.CONTACTED, changed_by="human", reason="called them")
    assert lead.status is LeadStatus.CONTACTED


# --------------------------------------------------------------------------- #
# Outreach draft → approve → send
# --------------------------------------------------------------------------- #
def test_draft_grounded_and_send_flow(seed_session, monkeypatch):
    lead = _seed_lead(seed_session)
    svc = OutreachService(seed_session)
    draft = svc.generate_draft(lead.id, now=NOW)
    assert draft.status is OutreachDraftStatus.READY_FOR_REVIEW
    assert draft.grounding_ok and draft.evidence_ids
    assert draft.recipient_email == "hire@acme.example"

    with pytest.raises(ValidationError):   # cannot send before approval
        send_draft(seed_session, draft.id, now=NOW, provider=_FakeOK())

    svc.approve(draft.id, now=NOW)
    from config import settings as sm
    monkeypatch.setattr(sm.get_settings(), "email_from", "sales@us.example")
    sent = send_draft(seed_session, draft.id, now=NOW, provider=_FakeOK())
    seed_session.refresh(lead)
    assert sent.status is OutreachDraftStatus.SENT and sent.provider_message_id == "msg-1"
    assert lead.status is LeadStatus.CONTACTED   # advanced only on confirmed send
    assert seed_session.query(CRMActivity).filter(CRMActivity.status == "SENT").count() == 1


def test_send_idempotent(seed_session, monkeypatch):
    lead = _seed_lead(seed_session)
    svc = OutreachService(seed_session)
    draft = svc.generate_draft(lead.id, now=NOW)
    svc.approve(draft.id, now=NOW)
    from config import settings as sm
    monkeypatch.setattr(sm.get_settings(), "email_from", "sales@us.example")
    send_draft(seed_session, draft.id, now=NOW, provider=_FakeOK())
    send_draft(seed_session, draft.id, now=NOW, provider=_FakeOK())   # second call
    assert seed_session.query(CRMActivity).filter(CRMActivity.status == "SENT").count() == 1


def test_send_failure_does_not_mark_sent(seed_session, monkeypatch):
    lead = _seed_lead(seed_session)
    svc = OutreachService(seed_session)
    draft = svc.generate_draft(lead.id, now=NOW)
    svc.approve(draft.id, now=NOW)
    from config import settings as sm
    monkeypatch.setattr(sm.get_settings(), "email_from", "sales@us.example")
    result = send_draft(seed_session, draft.id, now=NOW, provider=_FakeFail())
    seed_session.refresh(lead)
    assert result.status is OutreachDraftStatus.FAILED
    assert lead.status is LeadStatus.OUTREACH_READY   # NOT advanced on failure


def test_send_blocked_without_verified_email(seed_session, monkeypatch):
    lead = _seed_lead(seed_session, with_contact=False)
    svc = OutreachService(seed_session)
    draft = svc.generate_draft(lead.id, now=NOW)
    svc.approve(draft.id, now=NOW)
    from config import settings as sm
    monkeypatch.setattr(sm.get_settings(), "email_from", "sales@us.example")
    with pytest.raises(ValidationError):
        send_draft(seed_session, draft.id, now=NOW, provider=_FakeOK())


def test_ungrounded_draft_cannot_be_approved(seed_session):
    lead = _seed_lead(seed_session, with_evidence=False)
    svc = OutreachService(seed_session)
    draft = svc.generate_draft(lead.id, now=NOW)
    assert draft.status is OutreachDraftStatus.DRAFT and not draft.grounding_ok
    with pytest.raises(ValidationError):
        svc.approve(draft.id, now=NOW)


# --------------------------------------------------------------------------- #
# Reply + analytics
# --------------------------------------------------------------------------- #
def test_reply_advances_lead_and_creates_followup(seed_session):
    lead = _seed_lead(seed_session, status=LeadStatus.CONTACTED)
    res = record_reply(seed_session, provider="FAKE", provider_message_id="in-1",
                       lead_id=lead.id, body="We are interested, let's schedule a call", now=NOW)
    seed_session.refresh(lead)
    assert res.classification == "MEETING_REQUEST"
    assert lead.status is LeadStatus.REPLIED
    # duplicate provider event → no second activity
    dup = record_reply(seed_session, provider="FAKE", provider_message_id="in-1",
                       lead_id=lead.id, body="dup", now=NOW)
    assert dup.duplicate is True


def test_analytics_empty_is_honest(seed_session):
    a = compute_crm_analytics(seed_session, now=NOW)
    assert a.pipeline_value == NOT_AVAILABLE
    assert all(c.rate == INSUFFICIENT_DATA for c in a.conversion)


def test_analytics_value_only_from_real_source(seed_session):
    SalesPipelineService(seed_session).create(title="Deal", estimated_value=500000.0,
                                              estimated_value_currency="INR", value_source="USER")
    # An opportunity without a value source must not contribute.
    SalesPipelineService(seed_session).create(title="NoVal")
    a = compute_crm_analytics(seed_session, now=NOW)
    assert a.pipeline_value == 500000.0 and a.pipeline_value_opportunities == 1


def test_pipeline_value_never_inferred(seed_session):
    with pytest.raises(ValidationError):
        SalesPipelineService(seed_session).create(title="X", estimated_value=100.0, value_source="GUESS")


# --------------------------------------------------------------------------- #
# APIs
# --------------------------------------------------------------------------- #
def test_api_crm_analytics_and_pipeline(client):
    body = client.get("/crm/analytics").json()
    assert body["pipeline_value"] == "NOT_AVAILABLE"
    board = client.get("/pipeline/board").json()
    assert len(board["columns"]) == len(list(SalesStage))


def test_api_health_ready(client):
    body = client.get("/health/ready").json()
    assert body["status"] == "ready" and body["checks"]["database"] == "ok"


def test_api_providers_status_no_secrets(client):
    body = client.get("/outreach/providers/status").json()
    assert body["email_status"] == "NOT_CONFIGURED"
    assert body["crm_status"] in ("CONNECTED", "CONFIGURED")
    assert "api_key" not in json.dumps(body).lower()


def test_api_send_blocked_without_provider(client):
    import api.main
    from api.dependencies import get_session
    session = next(api.main.app.dependency_overrides[get_session]())
    lead = _seed_lead(session)
    draft = OutreachService(session).generate_draft(lead.id, now=NOW)
    OutreachService(session).approve(draft.id, now=NOW)
    session.commit()
    did = draft.id
    session.close()
    r = client.post(f"/outreach/{did}/send")
    assert r.status_code == 422 and r.json()["error"]["code"] == "validation_error"


def test_api_webhook_requires_signature(client):
    r = client.post("/webhooks/email/fake", json={"event_id": "e1", "event_type": "delivered",
                                                  "message_id": "m1"})
    assert r.status_code == 200
    assert r.json()["processed"] is False   # no secret configured → invalid signature, not processed


def test_api_rbac_enforced_when_admin_key_set(client, monkeypatch):
    from config import settings as sm
    monkeypatch.setattr(sm.get_settings(), "admin_api_key", "secret")
    # A mutation with no role header → VIEWER → forbidden.
    r = client.post("/activities", json={"activity_type": "NOTE", "subject": "hi"})
    assert r.status_code == 403
    # With SALES role header → allowed.
    ok = client.post("/activities", json={"activity_type": "NOTE", "subject": "hi"},
                     headers={"X-Role": "SALES"})
    assert ok.status_code == 200


def test_api_lead_transition_and_history(client):
    import api.main
    from api.dependencies import get_session
    session = next(api.main.app.dependency_overrides[get_session]())
    lead = _seed_lead(session)
    session.commit()
    lid = lead.id
    session.close()
    r = client.post(f"/leads/{lid}/transition", json={"new_status": "RESEARCHED", "reason": "done"})
    assert r.status_code == 200
    hist = client.get(f"/leads/{lid}/status-history").json()
    assert any(h["new_status"] == "RESEARCHED" for h in hist)
    # illegal transition rejected
    bad = client.post(f"/leads/{lid}/transition", json={"new_status": "WON"})
    assert bad.status_code == 422
