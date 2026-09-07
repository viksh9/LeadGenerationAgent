"""Central audit trail (§31). Every important CRM action records who/what/when/
old/new/source/reason + optional external provider id + correlation id. Values are
stringified and length-capped; secrets are never written here."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy.orm import Session

from database.models import AuditLog, utcnow

_MAX = 4000


def _fmt(value) -> str | None:
    if value is None:
        return None
    text = value if isinstance(value, str) else str(value)
    return text[:_MAX]


def record_audit(
    session: Session,
    *,
    entity_type: str,
    action: str,
    entity_id: int | None = None,
    actor: str = "SYSTEM",
    old_value=None,
    new_value=None,
    source: str | None = None,
    reason: str | None = None,
    external_provider_id: str | None = None,
    request_id: str | None = None,
    now: datetime | None = None,
) -> AuditLog:
    """Append an immutable audit record. Callers pass already-sanitized values —
    never raw provider payloads or credentials."""
    entry = AuditLog(
        entity_type=entity_type[:48],
        entity_id=entity_id,
        action=action[:64],
        actor=(actor or "SYSTEM")[:64],
        old_value=_fmt(old_value),
        new_value=_fmt(new_value),
        source=(source or None) and source[:64],
        reason=_fmt(reason),
        external_provider_id=(external_provider_id or None) and external_provider_id[:255],
        request_id=(request_id or None) and request_id[:64],
        created_at=now or utcnow(),
    )
    session.add(entry)
    session.flush()
    return entry
