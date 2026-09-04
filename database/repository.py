"""Repository functions for the Lead store.

These are thin, session-based helpers that keep all SQLAlchemy usage out of the
API layer. Each function takes an explicit `Session` so it is trivial to test
against an isolated database. Raw database errors are translated into domain
`ValidationError`s; missing records are handled gracefully (None / False) rather
than raising.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError, StatementError
from sqlalchemy.orm import Session

from config.exceptions import ValidationError
from database.models import Lead, LeadPriority, LeadStatus, utcnow
from database.session import create_session_factory, get_engine, init_db, session_scope

__all__ = [
    "create_lead",
    "get_lead",
    "list_leads",
    "update_lead",
    "delete_lead",
    "create_session_factory",
    "get_engine",
    "init_db",
    "session_scope",
]

# Fields a caller may set on create/update. Excludes server-managed columns.
_WRITABLE_FIELDS: frozenset[str] = frozenset(
    {
        "company_name",
        "industry",
        "location",
        "company_size",
        "company_website",
        "signal_type",
        "signal_title",
        "signal_description",
        "signal_date",
        "source_name",
        "source_url",
        "technologies",
        "project_name",
        "project_value",
        "estimated_hiring",
        "hiring_roles",
        "poc_name",
        "poc_title",
        "poc_linkedin_url",
        "public_contact",
        "signal_confidence",
        "lead_score",
        "lead_priority",
        "opportunity_summary",
        "recommended_action",
        "recommended_pitch",
        "status",
        "last_verified_at",
    }
)


def _filter_fields(fields: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in fields.items() if key in _WRITABLE_FIELDS}


def create_lead(session: Session, **fields: Any) -> Lead:
    """Insert a new lead. ``company_name`` is required.

    Raises ``ValidationError`` for a missing company name or any constraint
    violation (e.g. out-of-range score, negative hiring count).
    """
    payload = _filter_fields(fields)
    company_name = (payload.get("company_name") or "").strip()
    if not company_name:
        raise ValidationError("company_name is required")
    payload["company_name"] = company_name
    payload.setdefault("technologies", [])
    payload.setdefault("hiring_roles", [])

    lead = Lead(**payload)
    session.add(lead)
    try:
        session.flush()
    except (IntegrityError, StatementError) as exc:
        session.rollback()
        raise ValidationError(f"Invalid lead data: {exc.orig or exc}") from exc
    session.commit()
    session.refresh(lead)
    return lead


def get_lead(session: Session, lead_id: int) -> Lead | None:
    """Return the lead with ``lead_id`` or ``None`` if it does not exist."""
    return session.get(Lead, lead_id)


def list_leads(
    session: Session,
    *,
    status: LeadStatus | str | None = None,
    priority: LeadPriority | str | None = None,
    min_score: float | None = None,
    limit: int = 50,
    offset: int = 0,
) -> list[Lead]:
    """List leads, most recently updated first, with optional filters."""
    stmt = select(Lead)
    if status is not None:
        stmt = stmt.where(Lead.status == status)
    if priority is not None:
        stmt = stmt.where(Lead.lead_priority == priority)
    if min_score is not None:
        stmt = stmt.where(Lead.lead_score >= min_score)
    stmt = stmt.order_by(Lead.updated_at.desc(), Lead.id.desc()).offset(offset).limit(limit)
    return list(session.scalars(stmt))


def update_lead(session: Session, lead_id: int, **fields: Any) -> Lead | None:
    """Update writable fields on a lead. Returns ``None`` if it does not exist.

    Raises ``ValidationError`` on constraint violations.
    """
    lead = session.get(Lead, lead_id)
    if lead is None:
        return None
    updates = _filter_fields(fields)
    if "company_name" in updates:
        company_name = (updates["company_name"] or "").strip()
        if not company_name:
            raise ValidationError("company_name cannot be empty")
        updates["company_name"] = company_name
    for key, value in updates.items():
        setattr(lead, key, value)
    lead.updated_at = utcnow()
    try:
        session.flush()
    except (IntegrityError, StatementError) as exc:
        session.rollback()
        raise ValidationError(f"Invalid lead data: {exc.orig or exc}") from exc
    session.commit()
    session.refresh(lead)
    return lead


def delete_lead(session: Session, lead_id: int) -> bool:
    """Delete a lead. Returns ``True`` if a row was removed, ``False`` if absent."""
    lead = session.get(Lead, lead_id)
    if lead is None:
        return False
    session.delete(lead)
    session.commit()
    return True
