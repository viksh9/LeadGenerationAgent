"""Persistence helpers for deduplication: review queue + canonical stats.

Business logic stays here (out of route handlers). No public API is added.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from config.deduplication import DEFAULT_DEDUP_CONFIG
from database.models import (
    DataProvenance,
    DuplicateStatus,
    JobDuplicateCandidate,
    JobRecord,
    JobSourceReference,
)


def list_pending_duplicates(
    session: Session, *, provenance: Optional[DataProvenance] = None, limit: int = 50
) -> list[JobDuplicateCandidate]:
    stmt = select(JobDuplicateCandidate).where(JobDuplicateCandidate.status == DuplicateStatus.PENDING)
    if provenance is not None:
        stmt = stmt.where(JobDuplicateCandidate.data_provenance == provenance)
    stmt = stmt.order_by(JobDuplicateCandidate.match_score.desc()).limit(limit)
    return list(session.scalars(stmt))


def approve_duplicate(session: Session, candidate_id: int) -> bool:
    cand = session.get(JobDuplicateCandidate, candidate_id)
    if cand is None:
        return False
    cand.status = DuplicateStatus.APPROVED   # actual re-merge is a later stage
    session.commit()
    return True


def reject_duplicate(session: Session, candidate_id: int) -> bool:
    cand = session.get(JobDuplicateCandidate, candidate_id)
    if cand is None:
        return False
    cand.status = DuplicateStatus.REJECTED
    session.commit()
    return True


def dedup_stats(session: Session, *, provenance: DataProvenance = DataProvenance.REAL, now: Optional[datetime] = None) -> dict:
    """Canonical vs raw counts for the dashboard contract (§46).

    canonical_job_count: unique jobs. source_reference_count: source observations.
    """
    now = now or datetime.now(timezone.utc).replace(tzinfo=None)
    canonical = session.scalar(
        select(func.count()).select_from(JobRecord).where(JobRecord.data_provenance == provenance)
    ) or 0
    refs = session.scalar(
        select(func.count())
        .select_from(JobSourceReference)
        .join(JobRecord, JobSourceReference.job_record_id == JobRecord.id)
        .where(JobRecord.data_provenance == provenance)
    ) or 0
    recent_cutoff = now - timedelta(days=DEFAULT_DEDUP_CONFIG.recent_days)
    recent = session.scalar(
        select(func.count()).select_from(JobRecord)
        .where(JobRecord.data_provenance == provenance, JobRecord.published_at >= recent_cutoff)
    ) or 0
    return {
        "canonical_job_count": int(canonical),
        "source_reference_count": int(refs),
        "recent_canonical_jobs": int(recent),
        "duplicate_rate": round(1 - (canonical / refs), 3) if refs else 0.0,
    }
