"""Secure webhook ingestion (§39, §40).

Real provider events only. Every webhook is verified (HMAC signature + timestamp
tolerance to stop replay), then deduplicated by ``(provider, provider_event_id)``
so repeated delivery never creates duplicate CRM activities. Unsigned/invalid
payloads are recorded as INVALID and NOT processed — arbitrary payloads are never
trusted. Delivery/bounce/reply events update real records; nothing is simulated.
"""

from __future__ import annotations

import hashlib
import hmac
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from crm.activities import CRMActivityService
from database.models import (
    ActivityDirection,
    ActivityStatus,
    ActivityType,
    OutreachDraft,
    OutreachDraftStatus,
    WebhookEvent,
    WebhookStatus,
    utcnow,
)
from outreach.reply import record_reply

# Event-type buckets (case-insensitive substring match on the provider's type).
_REPLY_EVENTS = ("reply", "inbound", "inbound_email")
_DELIVERED_EVENTS = ("delivered", "delivery")
_FAILED_EVENTS = ("bounce", "bounced", "dropped", "failed", "failure", "spamreport")


@dataclass
class WebhookResult:
    event: WebhookEvent
    processed: bool
    duplicate: bool = False
    detail: str | None = None


def verify_signature(
    secret: str | None,
    *,
    payload: bytes,
    signature_header: str | None,
    timestamp_header: str | None,
    tolerance_seconds: int,
    now_ts: float,
) -> bool:
    """Constant-time HMAC-SHA256 verification of ``"{timestamp}.{payload}"`` with a
    timestamp-freshness (replay) check. Returns False for any missing/invalid part
    or a stale timestamp. When no secret is configured, ALL requests fail closed."""
    if not secret or not signature_header or not timestamp_header:
        return False
    try:
        ts = float(timestamp_header)
    except (TypeError, ValueError):
        return False
    if abs(now_ts - ts) > tolerance_seconds:
        return False   # replay / stale
    signed = f"{timestamp_header}.".encode() + payload
    expected = hmac.new(secret.encode(), signed, hashlib.sha256).hexdigest()
    provided = signature_header.split("=", 1)[-1].strip()   # tolerate "sha256=..." form
    return hmac.compare_digest(expected, provided)


def _payload_hash(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def process_webhook(
    session: Session,
    *,
    provider: str,
    provider_event_id: str,
    event_type: str | None,
    data: dict,
    signature_valid: bool,
    payload: bytes = b"",
    now: datetime | None = None,
) -> WebhookResult:
    """Record + (if valid) process one webhook event. Idempotent by event id."""
    now = now or utcnow()

    existing = session.execute(
        select(WebhookEvent).where(
            WebhookEvent.provider == provider,
            WebhookEvent.provider_event_id == provider_event_id,
        )
    ).scalars().first()
    if existing is not None:
        return WebhookResult(existing, processed=False, duplicate=True, detail="duplicate event")

    event = WebhookEvent(
        provider=provider, event_type=event_type, provider_event_id=provider_event_id,
        signature_valid=signature_valid, payload_hash=_payload_hash(payload) if payload else None,
        status=WebhookStatus.RECEIVED, received_at=now,
    )
    session.add(event)
    session.flush()

    if not signature_valid:
        event.status = WebhookStatus.INVALID
        event.error = "signature verification failed"
        session.flush()
        return WebhookResult(event, processed=False, detail="invalid signature")

    try:
        detail = _dispatch(session, provider=provider, event_type=event_type, data=data, event=event, now=now)
        event.status = WebhookStatus.PROCESSED
        event.processed_at = now
        session.flush()
        return WebhookResult(event, processed=True, detail=detail)
    except Exception as exc:  # noqa: BLE001
        event.status = WebhookStatus.FAILED
        event.error = f"{type(exc).__name__}: {exc}"[:500]
        session.flush()
        return WebhookResult(event, processed=False, detail=event.error)


def _dispatch(session, *, provider, event_type, data, event, now) -> str:
    etype = (event_type or "").lower()

    if any(k in etype for k in _REPLY_EVENTS):
        res = record_reply(
            session, provider=provider,
            provider_message_id=str(data.get("message_id") or data.get("id") or event.provider_event_id),
            in_reply_to=data.get("in_reply_to"), thread_id=data.get("thread_id"),
            lead_id=data.get("lead_id"), subject=data.get("subject"), body=data.get("body"),
            now=now,
        )
        event.related_lead_id = res.activity.lead_id
        return f"reply recorded ({res.classification})"

    if any(k in etype for k in _DELIVERED_EVENTS):
        return _delivery_status(session, data, ActivityStatus.DELIVERED, provider, event, now)

    if any(k in etype for k in _FAILED_EVENTS):
        return _delivery_status(session, data, ActivityStatus.FAILED, provider, event, now)

    return "event acknowledged (no handler)"


def _delivery_status(session, data, status, provider, event, now) -> str:
    message_id = str(data.get("message_id") or data.get("id") or "")
    draft = None
    if message_id:
        draft = session.execute(
            select(OutreachDraft).where(OutreachDraft.provider_message_id == message_id)
        ).scalars().first()
    if draft is None:
        return "delivery event for unknown message"
    event.related_draft_id = draft.id
    event.related_lead_id = draft.lead_id
    CRMActivityService(session).log(
        activity_type=ActivityType.EMAIL, lead_id=draft.lead_id, company_id=draft.company_id,
        contact_id=draft.contact_id, direction=ActivityDirection.OUTBOUND, status=status,
        subject=f"Email {status.value.lower()}", source=provider,
        external_id=f"{message_id}:{status.value}", occurred_at=now, created_by="PROVIDER", now=now,
    )
    if status is ActivityStatus.FAILED and draft.status == OutreachDraftStatus.SENT:
        draft.error = "provider reported bounce/failure"
    return f"delivery status {status.value} recorded"
