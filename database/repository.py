"""Repository functions for the Lead store.

These are thin, session-based helpers that keep all SQLAlchemy usage out of the
API layer. Each function takes an explicit `Session` so it is trivial to test
against an isolated database. Raw database errors are translated into domain
`ValidationError`s; missing records are handled gracefully (None / False) rather
than raising.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import String, cast, func, or_, select
from sqlalchemy.exc import IntegrityError, StatementError
from sqlalchemy.orm import Session

from config.exceptions import ValidationError
from database.integrity import guard_lead_fields
from database.models import Lead, LeadPriority, LeadStatus, utcnow
from database.session import create_session_factory, get_engine, init_db, session_scope

__all__ = [
    "create_lead",
    "get_lead",
    "list_leads",
    "query_leads",
    "update_lead",
    "delete_lead",
    "find_duplicate_lead",
    "create_session_factory",
    "get_engine",
    "init_db",
    "session_scope",
]

# Fields a caller may set on create/update. Excludes server-managed columns.
_WRITABLE_FIELDS: frozenset[str] = frozenset(
    {
        "company_name",
        "normalized_company_name",
        "company_domain",
        "company_type",
        "industry",
        "location",
        "location_all",
        "company_size",
        "company_website",
        "it_job_count",
        "recent_job_count",
        "hiring_intensity",
        "primary_target_role",
        "company_signals",
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
        "data_provenance",
        "source_count",
        "evidence",
        "last_signal_date",
        "source_reliability",
        "evidence_confidence",
        "freshness_score",
        "independent_support_count",
        "verification_status",
        "lead_readiness",
        "verification_reason",
        "verification_version",
        "verified_at",
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

    # Real-data-only guard: in production/staging reject synthetic provenance and
    # REAL leads that carry no source-backed evidence. No-op in dev/test.
    guard_lead_fields(payload)

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


# Whitelisted sort columns — never interpolate a client-supplied field name.
_SORT_COLUMNS = {
    "lead_score": Lead.lead_score,
    "created_at": Lead.created_at,
    "updated_at": Lead.updated_at,
    "signal_date": Lead.signal_date,
    "company_name": Lead.company_name,
}


def query_leads(
    session: Session,
    *,
    search: str | None = None,
    industry: str | None = None,
    location: str | None = None,
    signal_type: Any = None,
    lead_priority: Any = None,
    status: Any = None,
    min_score: float | None = None,
    max_score: float | None = None,
    technology: str | None = None,
    provenance: Any = None,
    sort_by: str = "lead_score",
    sort_order: str = "desc",
    page: int = 1,
    page_size: int = 20,
) -> tuple[list[Lead], int]:
    """Filter/search/sort/paginate leads at the database level.

    Returns ``(items, total)`` where ``total`` is the unpaginated match count.
    All filtering happens in SQL (no full-table load); sort fields are
    whitelisted and enum filters are typed, so no arbitrary SQL is accepted.
    """
    conditions = []
    if search:
        like = f"%{search.lower()}%"
        conditions.append(
            or_(
                func.lower(Lead.company_name).like(like),
                func.lower(func.coalesce(Lead.signal_title, "")).like(like),
                func.lower(func.coalesce(Lead.signal_description, "")).like(like),
                func.lower(func.coalesce(Lead.project_name, "")).like(like),
            )
        )
    if industry:
        conditions.append(func.lower(Lead.industry) == industry.lower())
    if location:
        conditions.append(func.lower(Lead.location) == location.lower())
    if signal_type is not None:
        conditions.append(Lead.signal_type == signal_type)
    if lead_priority is not None:
        conditions.append(Lead.lead_priority == lead_priority)
    if status is not None:
        conditions.append(Lead.status == status)
    if provenance is not None:
        conditions.append(Lead.data_provenance == provenance)
    if min_score is not None:
        conditions.append(Lead.lead_score >= min_score)
    if max_score is not None:
        conditions.append(Lead.lead_score <= max_score)
    if technology:
        # technologies is a JSON array column; match the quoted value in its text.
        conditions.append(func.lower(cast(Lead.technologies, String)).like(f"%{technology.lower()}%"))

    base = select(Lead)
    for condition in conditions:
        base = base.where(condition)

    total = session.scalar(select(func.count()).select_from(base.subquery())) or 0

    column = _SORT_COLUMNS.get(sort_by, Lead.lead_score)
    ordering = column.asc() if sort_order == "asc" else column.desc()
    stmt = base.order_by(ordering, Lead.id.desc()).offset((page - 1) * page_size).limit(page_size)
    return list(session.scalars(stmt)), int(total)


def find_duplicate_lead(
    session: Session,
    *,
    company_name: str,
    signal_title: str | None = None,
    source_url: str | None = None,
) -> Lead | None:
    """Find an existing lead matching the dedup key (company + signal/source).

    Matching narrows on ``signal_title`` and ``source_url`` when supplied, so an
    identical re-analysis maps to the same row instead of creating a duplicate.
    Returns the most recent match, or ``None``.
    """
    if not company_name:
        return None
    stmt = select(Lead).where(Lead.company_name == company_name)
    if signal_title is not None:
        stmt = stmt.where(Lead.signal_title == signal_title)
    if source_url is not None:
        stmt = stmt.where(Lead.source_url == source_url)
    stmt = stmt.order_by(Lead.id.desc())
    return session.scalars(stmt).first()


def find_company_lead(
    session: Session,
    *,
    normalized_company_name: str,
    provenance: Any,
) -> Lead | None:
    """Find the company-level lead for a normalized company + provenance.

    Company-level aggregation keeps ONE lead per (normalized company, provenance),
    so re-aggregation refreshes that row rather than creating duplicates.
    """
    if not normalized_company_name:
        return None
    stmt = (
        select(Lead)
        .where(Lead.normalized_company_name == normalized_company_name)
        .where(Lead.data_provenance == provenance)
        .order_by(Lead.id.asc())
    )
    return session.scalars(stmt).first()


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
