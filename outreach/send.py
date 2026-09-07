"""Outreach send flow (§10, §11, §12).

Enforces, in order: APPROVED status → EMAIL channel only (never auto-sends
LinkedIn, §8) → verified business email recipient → configured provider → rate
limit + daily cap → idempotency lock. Only when the provider CONFIRMS the send do
we mark the draft SENT, log a SENT activity, and advance the lead to CONTACTED
(via the event-gated lifecycle). On any failure the draft is FAILED, no lead
advances, and nothing is fabricated (§11).
"""

from __future__ import annotations

import threading
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from config.exceptions import NotFoundError, ValidationError
from config.settings import get_settings
from crm.activities import CRMActivityService
from crm.audit import record_audit
from crm.lifecycle import LeadLifecycleService
from crm.providers.email_provider import BaseEmailProvider, build_email_provider
from database.models import (
    ActivityDirection,
    ActivityStatus,
    ActivityType,
    DecisionMaker,
    LeadStatus,
    OutreachChannel,
    OutreachDraft,
    OutreachDraftStatus,
    utcnow,
)
from outreach.contacts import has_verified_business_email, is_valid_email

# Per-draft in-process send locks (prevent double-send from double clicks/retries).
_SEND_LOCKS: dict[int, threading.Lock] = {}
_LOCKS_GUARD = threading.Lock()

# Simple per-process minute limiter shared across sends.
_MINUTE_WINDOW: list[float] = []
_RATE_GUARD = threading.Lock()


def _lock_for(draft_id: int) -> threading.Lock:
    with _LOCKS_GUARD:
        lock = _SEND_LOCKS.get(draft_id)
        if lock is None:
            lock = threading.Lock()
            _SEND_LOCKS[draft_id] = lock
        return lock


def _sent_today(session: Session, now: datetime) -> int:
    start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    return int(session.execute(
        select(func.count(OutreachDraft.id)).where(
            OutreachDraft.status == OutreachDraftStatus.SENT,
            OutreachDraft.sent_at >= start,
        )
    ).scalar() or 0)


def _check_minute_rate(limit_per_minute: int, *, ts: float) -> bool:
    if limit_per_minute <= 0:
        return True
    with _RATE_GUARD:
        cutoff = ts - 60
        while _MINUTE_WINDOW and _MINUTE_WINDOW[0] < cutoff:
            _MINUTE_WINDOW.pop(0)
        if len(_MINUTE_WINDOW) >= limit_per_minute:
            return False
        _MINUTE_WINDOW.append(ts)
        return True


def send_draft(
    session: Session,
    draft_id: int,
    *,
    actor: str = "human",
    provider: BaseEmailProvider | None = None,
    now: datetime | None = None,
    _clock_ts: float | None = None,
) -> OutreachDraft:
    """Send an APPROVED email draft through a configured provider, with full
    safety + idempotency. Raises ValidationError when any precondition fails."""
    now = now or utcnow()
    settings = get_settings()

    draft = session.get(OutreachDraft, draft_id)
    if draft is None:
        raise NotFoundError(f"Outreach draft {draft_id} not found.")

    # Idempotency: already sent → return unchanged (no duplicate send).
    if draft.status == OutreachDraftStatus.SENT:
        return draft
    if draft.status != OutreachDraftStatus.APPROVED:
        raise ValidationError(f"Only APPROVED drafts can be sent (current: {draft.status.value}).")
    if draft.channel != OutreachChannel.EMAIL:
        raise ValidationError(
            f"Only EMAIL sending is implemented; {draft.channel.value} must be handled manually."
        )

    # Recipient validation — verified business email required by policy (§10).
    contact = session.get(DecisionMaker, draft.contact_id) if draft.contact_id else None
    recipient = draft.recipient_email
    if settings.outreach_require_verified_email:
        if contact is None or not has_verified_business_email(contact):
            raise ValidationError(
                "Recipient has no source-verified business email; refusing to send."
            )
        recipient = contact.business_email
    if not is_valid_email(recipient):
        raise ValidationError("Invalid or missing recipient email; refusing to send.")

    # Provider must be configured (§10.4).
    provider = provider or build_email_provider(settings)
    if provider is None:
        raise ValidationError("Email provider is NOT_CONFIGURED; cannot send.")

    # Daily cap + per-minute rate limit (§11 rate limit; never mass-sends).
    if _sent_today(session, now) >= settings.email_daily_limit:
        raise ValidationError(f"Daily send limit ({settings.email_daily_limit}) reached.")
    ts = _clock_ts if _clock_ts is not None else now.timestamp()
    if not _check_minute_rate(settings.email_rate_per_minute, ts=ts):
        raise ValidationError("Send rate limit exceeded; try again shortly.")

    # Idempotency lock (double-click / retry / scheduler restart protection, §12).
    lock = _lock_for(draft_id)
    if not lock.acquire(blocking=False):
        raise ValidationError("A send is already in progress for this draft.")
    try:
        session.refresh(draft)
        if draft.status == OutreachDraftStatus.SENT:   # re-check under lock
            return draft

        result = provider.send(
            to=recipient, subject=draft.subject or "",
            body=draft.message or "", from_addr=settings.email_from or "",
        )
        activities = CRMActivityService(session)
        if result.success:
            draft.status = OutreachDraftStatus.SENT
            draft.sent_at = now
            draft.provider = result.provider
            draft.provider_message_id = result.provider_message_id
            draft.error = None
            draft.updated_at = now
            session.flush()
            activities.log(
                activity_type=ActivityType.EMAIL, lead_id=draft.lead_id, company_id=draft.company_id,
                contact_id=draft.contact_id, direction=ActivityDirection.OUTBOUND,
                status=ActivityStatus.SENT, subject=draft.subject, source=result.provider,
                external_id=result.provider_message_id, created_by=actor, occurred_at=now, now=now,
            )
            record_audit(session, entity_type="outreach_draft", entity_id=draft.id, action="SEND",
                         actor=actor, new_value="SENT", source=result.provider,
                         external_provider_id=result.provider_message_id, now=now)
            # Advance the lead ONLY on confirmed send (event-gated lifecycle).
            if draft.lead_id:
                try:
                    LeadLifecycleService(session).transition(
                        draft.lead_id, LeadStatus.CONTACTED, changed_by="SYSTEM",
                        source="SEND_CONFIRMED", reason="Outreach email sent", now=now,
                    )
                except ValidationError:
                    # Lead not in a state that can advance to CONTACTED — leave as-is;
                    # the send itself is still real and recorded.
                    pass
        else:
            draft.status = OutreachDraftStatus.FAILED
            draft.error = result.error
            draft.updated_at = now
            session.flush()
            activities.log(
                activity_type=ActivityType.EMAIL, lead_id=draft.lead_id, company_id=draft.company_id,
                contact_id=draft.contact_id, direction=ActivityDirection.OUTBOUND,
                status=ActivityStatus.FAILED, subject=draft.subject, source=result.provider,
                body_reference=result.error, created_by=actor, occurred_at=now, now=now,
            )
            record_audit(session, entity_type="outreach_draft", entity_id=draft.id, action="SEND_FAILED",
                         actor=actor, new_value="FAILED", reason=result.error, now=now)
        session.flush()
        return draft
    finally:
        lock.release()
