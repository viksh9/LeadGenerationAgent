"""Webhook ingestion endpoints (§39, §40).

Public (no session auth) but cryptographically verified: every request must carry
a valid HMAC signature + fresh timestamp (replay protection) computed with the
configured ``WEBHOOK_SECRET``. When the secret is unset, all requests fail closed.
Events are deduplicated by provider event id. Rate-limited to blunt abuse.
"""

from __future__ import annotations

import time

from fastapi import APIRouter, Depends, Header, Request
from sqlalchemy.orm import Session

from api.dependencies import get_session
from api.security import rate_limit
from api.schemas import WebhookAck
from config import get_settings
from config.exceptions import ValidationError
from crm.webhooks import process_webhook, verify_signature

router = APIRouter(prefix="/webhooks", tags=["webhooks"])

_webhook_limit = rate_limit("webhooks", 120)


@router.post("/email/{provider}", response_model=WebhookAck, summary="Ingest a signed email provider webhook")
async def email_webhook(
    provider: str,
    request: Request,
    session: Session = Depends(get_session),
    x_signature: str | None = Header(default=None),
    x_timestamp: str | None = Header(default=None),
    _rl=Depends(_webhook_limit),
) -> WebhookAck:
    settings = get_settings()
    raw = await request.body()

    valid = verify_signature(
        settings.webhook_secret, payload=raw, signature_header=x_signature,
        timestamp_header=x_timestamp, tolerance_seconds=settings.webhook_tolerance_seconds,
        now_ts=time.time(),
    )

    import json
    try:
        data = json.loads(raw.decode() or "{}")
    except (ValueError, UnicodeDecodeError) as exc:
        raise ValidationError("Invalid JSON webhook payload.") from exc
    if not isinstance(data, dict):
        raise ValidationError("Webhook payload must be a JSON object.")

    event_id = str(data.get("event_id") or data.get("id") or "")
    if not event_id:
        raise ValidationError("Webhook payload missing an event id.")
    event_type = data.get("event_type") or data.get("type")

    result = process_webhook(
        session, provider=provider, provider_event_id=event_id, event_type=event_type,
        data=data, signature_valid=valid, payload=raw,
    )
    session.commit()
    return WebhookAck(received=True, processed=result.processed, duplicate=result.duplicate,
                      detail=result.detail)
