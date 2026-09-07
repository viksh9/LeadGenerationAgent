"""Inbound reply handling (§14).

A reply is recorded ONLY from a real provider event (webhook / configured
mailbox). This module never scrapes mailboxes and never claims a reply exists
without provider evidence. On a real reply it: matches the lead/contact by
provider message/thread id, stores an EMAIL_REPLY CRM activity (deduped), moves
the lead to REPLIED (event-gated), classifies the message (grounded in its text),
and creates a REVIEW_REPLY follow-up task so a human reviews it.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from config.exceptions import ValidationError
from crm.activities import CRMActivityService
from crm.audit import record_audit
from crm.lifecycle import LeadLifecycleService
from database.models import (
    ActivityDirection,
    ActivityStatus,
    ActivityType,
    CRMActivity,
    FollowUpTask,
    FollowUpType,
    LeadStatus,
    OutreachDraft,
    utcnow,
)
from outreach.ai_reply import classify_reply


@dataclass
class ReplyResult:
    activity: CRMActivity
    classification: str
    quote: str | None
    lead_advanced: bool
    duplicate: bool = False


def _match_lead(session: Session, *, in_reply_to: str | None, thread_id: str | None,
                lead_id: int | None) -> tuple[int | None, int | None, int | None]:
    """Resolve (lead_id, company_id, contact_id) from the outbound message this
    reply threads to. Never guesses beyond real provider identifiers."""
    if lead_id is not None:
        return lead_id, None, None
    ref = in_reply_to or thread_id
    if ref:
        draft = session.execute(
            select(OutreachDraft).where(OutreachDraft.provider_message_id == ref)
        ).scalars().first()
        if draft is not None:
            return draft.lead_id, draft.company_id, draft.contact_id
    return None, None, None


def record_reply(
    session: Session,
    *,
    provider: str,
    provider_message_id: str,
    in_reply_to: str | None = None,
    thread_id: str | None = None,
    lead_id: int | None = None,
    contact_id: int | None = None,
    company_id: int | None = None,
    subject: str | None = None,
    body: str | None = None,
    occurred_at: datetime | None = None,
    now: datetime | None = None,
) -> ReplyResult:
    """Record a REAL inbound reply. Idempotent by (provider, provider_message_id)."""
    now = now or utcnow()
    if not provider_message_id:
        raise ValidationError("A provider message id is required to record a reply.")

    resolved_lead, resolved_company, resolved_contact = _match_lead(
        session, in_reply_to=in_reply_to, thread_id=thread_id, lead_id=lead_id
    )
    lead_id = lead_id or resolved_lead
    company_id = company_id or resolved_company
    contact_id = contact_id or resolved_contact

    activities = CRMActivityService(session)
    # Dedup: existing activity for this provider event → return it (no duplicate).
    existing = session.execute(
        select(CRMActivity).where(CRMActivity.source == provider,
                                  CRMActivity.external_id == provider_message_id)
    ).scalars().first()

    result = classify_reply(body)

    if existing is not None:
        return ReplyResult(existing, result.classification.value, result.quote,
                           lead_advanced=False, duplicate=True)

    activity = activities.log(
        activity_type=ActivityType.EMAIL_REPLY, lead_id=lead_id, company_id=company_id,
        contact_id=contact_id, direction=ActivityDirection.INBOUND, status=ActivityStatus.REPLIED,
        subject=(subject or "Reply received"),
        body_reference=f"[{result.classification.value}] {result.quote or ''}".strip(),
        source=provider, external_id=provider_message_id, occurred_at=occurred_at or now,
        created_by="PROVIDER", now=now,
    )

    lead_advanced = False
    if lead_id:
        try:
            LeadLifecycleService(session).transition(
                lead_id, LeadStatus.REPLIED, changed_by="SYSTEM", source="PROVIDER_REPLY",
                reason=f"Inbound reply classified {result.classification.value}", now=now,
            )
            lead_advanced = True
        except ValidationError:
            lead_advanced = False   # lead not in a state to advance; reply still recorded

        # A human should review every real reply.
        session.add(FollowUpTask(
            lead_id=lead_id, contact_id=contact_id, company_id=company_id,
            task_type=FollowUpType.REVIEW_REPLY, due_at=now,
            title=f"Review reply ({result.classification.value})",
            reason=result.quote, dedup_key=f"reply:{provider}:{provider_message_id}",
            created_by="SYSTEM", created_at=now,
        ))

    record_audit(session, entity_type="lead", entity_id=lead_id, action="REPLY_RECEIVED",
                 actor="PROVIDER", source=provider, external_provider_id=provider_message_id,
                 new_value=result.classification.value, now=now)
    session.flush()
    return ReplyResult(activity, result.classification.value, result.quote, lead_advanced)
