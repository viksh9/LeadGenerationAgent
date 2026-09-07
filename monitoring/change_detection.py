"""Deterministic change-detection engine for canonical jobs (§6, §7, §8).

Two layers:

* ``classify_job_change`` — a PURE function comparing a previous and current
  :class:`JobSnapshot` and returning a verdict (change type + significance +
  field-level diffs). Fully deterministic and unit-testable; no DB, no clock
  side effects.
* ``detect_job_changes`` — a driver that builds snapshots from REAL
  ``JobRecord`` rows, classifies them, and persists idempotent
  ``JobChangeEvent`` rows.

Key rule (§6): a job disappearing from a source is ``REMOVED_FROM_SOURCE`` — it
is NOT automatically ``CLOSED``. Only an explicit closed/expired source status
produces ``CLOSED``; later evidence may still reconcile it.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from database.models import (
    ChangeSignificance,
    ChangeType,
    DataProvenance,
    JobChangeEvent,
    JobRecord,
    JobStatus,
)

_CLOSED_STATUSES = {JobStatus.EXPIRED.value}
_ACTIVE_STATUSES = {JobStatus.ACTIVE.value, JobStatus.UNKNOWN.value}

# Field-level significance for UPDATED jobs (§8).
_FIELD_SIGNIFICANCE: dict[str, ChangeSignificance] = {
    "technologies": ChangeSignificance.MEDIUM,
    "location": ChangeSignificance.MEDIUM,
    "employment_type": ChangeSignificance.LOW,
    "salary": ChangeSignificance.LOW,
    "title": ChangeSignificance.LOW,
    "published_at": ChangeSignificance.LOW,
}
_SIG_ORDER = {
    ChangeSignificance.LOW: 0,
    ChangeSignificance.MEDIUM: 1,
    ChangeSignificance.HIGH: 2,
    ChangeSignificance.CRITICAL: 3,
}


@dataclass(frozen=True)
class JobSnapshot:
    """Immutable view of a canonical job at a point in time. Built only from
    REAL ``JobRecord`` columns."""

    canonical_job_id: int
    content_hash: str
    job_status: str = JobStatus.UNKNOWN.value
    company_id: int | None = None
    company_normalized_name: str | None = None
    title: str | None = None
    location: str | None = None
    technologies: tuple[str, ...] = ()
    salary_min: float | None = None
    salary_max: float | None = None
    employment_type: str | None = None
    published_at: datetime | None = None
    source_updated_at: datetime | None = None
    first_seen_at: datetime | None = None
    last_seen_at: datetime | None = None

    @classmethod
    def from_record(cls, rec: JobRecord) -> "JobSnapshot":
        techs = tuple(sorted(str(t).strip().lower() for t in (rec.technologies or []) if str(t).strip()))
        loc = " / ".join(p for p in (rec.city, rec.state, rec.country) if p) or rec.original_location
        return cls(
            canonical_job_id=rec.id,
            content_hash=rec.content_hash or "",
            job_status=(rec.job_status.value if hasattr(rec.job_status, "value") else str(rec.job_status)),
            company_id=None,
            company_normalized_name=rec.normalized_company_name,
            title=rec.normalized_title or rec.original_job_title,
            location=loc,
            technologies=techs,
            salary_min=rec.salary_min,
            salary_max=rec.salary_max,
            employment_type=rec.employment_type,
            published_at=rec.published_at,
            source_updated_at=rec.source_updated_at,
            first_seen_at=rec.first_seen_at,
            last_seen_at=rec.last_seen_at,
        )


@dataclass(frozen=True)
class FieldChange:
    field_name: str
    old_value: str | None
    new_value: str | None
    significance: ChangeSignificance


@dataclass(frozen=True)
class JobChangeVerdict:
    canonical_job_id: int
    change_type: ChangeType
    significance: ChangeSignificance
    field_changes: tuple[FieldChange, ...] = ()

    @property
    def is_meaningful(self) -> bool:
        return self.change_type is not ChangeType.UNCHANGED


def _fmt(value) -> str | None:
    if value is None:
        return None
    if isinstance(value, (list, tuple)):
        return ", ".join(str(v) for v in value) or None
    if isinstance(value, datetime):
        return value.date().isoformat()
    return str(value)


def _diff_fields(prev: JobSnapshot, curr: JobSnapshot) -> list[FieldChange]:
    changes: list[FieldChange] = []
    comparisons = [
        ("title", prev.title, curr.title),
        ("location", prev.location, curr.location),
        ("technologies", prev.technologies, curr.technologies),
        ("employment_type", prev.employment_type, curr.employment_type),
        ("salary", (prev.salary_min, prev.salary_max), (curr.salary_min, curr.salary_max)),
        ("published_at", prev.published_at, curr.published_at),
    ]
    for name, old, new in comparisons:
        if old != new:
            changes.append(
                FieldChange(
                    field_name=name,
                    old_value=_fmt(old),
                    new_value=_fmt(new),
                    significance=_FIELD_SIGNIFICANCE.get(name, ChangeSignificance.LOW),
                )
            )
    return changes


def _max_significance(items, default: ChangeSignificance) -> ChangeSignificance:
    best = default
    for sig in items:
        if _SIG_ORDER[sig] > _SIG_ORDER[best]:
            best = sig
    return best


def classify_job_change(
    previous: JobSnapshot | None,
    current: JobSnapshot | None,
    *,
    now: datetime,
    is_stale: bool = False,
    is_contradicted: bool = False,
) -> JobChangeVerdict:
    """Pure deterministic classification of a single job's change (§6, §7, §8).

    ``is_stale`` / ``is_contradicted`` are supplied by the freshness/evidence
    layers (this function does not compute them).
    """
    # Disappeared from source (§6): NOT closed.
    if previous is not None and current is None:
        return JobChangeVerdict(
            previous.canonical_job_id, ChangeType.REMOVED_FROM_SOURCE, ChangeSignificance.MEDIUM
        )
    # Brand new job.
    if previous is None and current is not None:
        return JobChangeVerdict(current.canonical_job_id, ChangeType.NEW, ChangeSignificance.MEDIUM)
    if previous is None and current is None:  # nothing to compare
        raise ValueError("classify_job_change requires at least one snapshot")

    assert previous is not None and current is not None
    jid = current.canonical_job_id

    prev_closed = previous.job_status in _CLOSED_STATUSES
    curr_closed = current.job_status in _CLOSED_STATUSES

    # Explicit closure / reopen via source status (§6, §7).
    if not prev_closed and curr_closed:
        return JobChangeVerdict(jid, ChangeType.CLOSED, ChangeSignificance.CRITICAL)
    if prev_closed and not curr_closed:
        return JobChangeVerdict(jid, ChangeType.REOPENED, ChangeSignificance.HIGH)

    if is_contradicted:
        return JobChangeVerdict(jid, ChangeType.CONTRADICTED, ChangeSignificance.CRITICAL)

    # Content change → UPDATED with field-level diffs.
    if previous.content_hash != current.content_hash:
        diffs = _diff_fields(previous, current)
        if diffs:
            sig = _max_significance((d.significance for d in diffs), ChangeSignificance.LOW)
            return JobChangeVerdict(jid, ChangeType.UPDATED, sig, tuple(diffs))
        # Hash differs but tracked fields identical → treat as minor update.
        return JobChangeVerdict(jid, ChangeType.UPDATED, ChangeSignificance.LOW)

    # No content change: stale or genuinely unchanged.
    if is_stale:
        return JobChangeVerdict(jid, ChangeType.STALE, ChangeSignificance.MEDIUM)
    return JobChangeVerdict(jid, ChangeType.UNCHANGED, ChangeSignificance.LOW)


# --------------------------------------------------------------------------- #
# Driver: persist idempotent JobChangeEvents from REAL records.
# --------------------------------------------------------------------------- #
def _existing_dedup_keys(session: Session, keys: list[str]) -> set[str]:
    if not keys:
        return set()
    rows = session.execute(
        select(JobChangeEvent.dedup_key).where(JobChangeEvent.dedup_key.in_(keys))
    ).scalars().all()
    return set(rows)


def _dedup_key(verdict: JobChangeVerdict, current: JobSnapshot | None, field_name: str | None = None) -> str:
    jid = verdict.canonical_job_id
    ct = verdict.change_type.value
    # Bind volatile change types to a stamp so a genuinely new occurrence re-fires,
    # while a repeated identical condition stays deduped.
    stamp = ""
    if current is not None:
        if verdict.change_type in (ChangeType.UPDATED,):
            stamp = f":{current.content_hash}"
        elif verdict.change_type in (ChangeType.REMOVED_FROM_SOURCE, ChangeType.REOPENED, ChangeType.STALE):
            seen = current.last_seen_at or current.published_at
            stamp = f":{seen.date().isoformat()}" if seen else ""
    if field_name:
        return f"job:{jid}:{ct}{stamp}:{field_name}"
    return f"job:{jid}:{ct}{stamp}"


@dataclass
class JobChangeSummary:
    new: int = 0
    updated: int = 0
    closed: int = 0
    removed: int = 0
    reopened: int = 0
    stale: int = 0
    contradicted: int = 0
    events: list[JobChangeEvent] = field(default_factory=list)

    @property
    def total(self) -> int:
        return self.new + self.updated + self.closed + self.removed + self.reopened + self.stale + self.contradicted


def detect_job_changes(
    session: Session,
    *,
    now: datetime,
    run_since: datetime | None = None,
    scheduler_run_id: int | None = None,
    previous_snapshots: dict[int, JobSnapshot] | None = None,
    stale_ids: set[int] | None = None,
    contradicted_ids: set[int] | None = None,
    provenance: DataProvenance = DataProvenance.REAL,
) -> JobChangeSummary:
    """Detect and persist job changes across REAL canonical jobs.

    When ``previous_snapshots`` is supplied (e.g. by the scheduler's prior-run
    store or a test), full UPDATED field diffs are produced. Otherwise change
    *types* are derived deterministically from the record's own cross-run
    columns (``first_seen_at`` / ``last_seen_at`` / ``job_status``), which are
    real observations — never fabricated.
    """
    stale_ids = stale_ids or set()
    contradicted_ids = contradicted_ids or set()
    summary = JobChangeSummary()

    records = session.execute(
        select(JobRecord).where(JobRecord.data_provenance == provenance)
    ).scalars().all()

    verdicts: list[tuple[JobChangeVerdict, JobSnapshot]] = []
    for rec in records:
        curr = JobSnapshot.from_record(rec)
        prev = (previous_snapshots or {}).get(rec.id)
        is_stale = rec.id in stale_ids
        is_contra = rec.id in contradicted_ids

        if prev is not None:
            verdict = classify_job_change(prev, curr, now=now, is_stale=is_stale, is_contradicted=is_contra)
        else:
            # No prior snapshot: derive type from real cross-run columns.
            verdict = _derive_from_columns(curr, now=now, run_since=run_since,
                                           is_stale=is_stale, is_contradicted=is_contra)
        if verdict.is_meaningful:
            verdicts.append((verdict, curr))

    # Idempotent persistence.
    candidate_keys: list[str] = []
    for verdict, curr in verdicts:
        if verdict.change_type is ChangeType.UPDATED and verdict.field_changes:
            candidate_keys.extend(_dedup_key(verdict, curr, fc.field_name) for fc in verdict.field_changes)
        else:
            candidate_keys.append(_dedup_key(verdict, curr))
    existing = _existing_dedup_keys(session, candidate_keys)

    for verdict, curr in verdicts:
        rows = _build_events(verdict, curr, scheduler_run_id, existing, provenance)
        for row in rows:
            session.add(row)
            existing.add(row.dedup_key)
            summary.events.append(row)
            _bump(summary, verdict.change_type)
    if summary.events:
        session.flush()
    return summary


def _derive_from_columns(
    curr: JobSnapshot, *, now: datetime, run_since: datetime | None,
    is_stale: bool, is_contradicted: bool,
) -> JobChangeVerdict:
    jid = curr.canonical_job_id
    if is_contradicted:
        return JobChangeVerdict(jid, ChangeType.CONTRADICTED, ChangeSignificance.CRITICAL)
    if curr.job_status in _CLOSED_STATUSES:
        return JobChangeVerdict(jid, ChangeType.CLOSED, ChangeSignificance.CRITICAL)
    # New since last cycle.
    if run_since is not None and curr.first_seen_at is not None and curr.first_seen_at >= run_since:
        return JobChangeVerdict(jid, ChangeType.NEW, ChangeSignificance.MEDIUM)
    # Not seen this cycle → disappeared from source (not closed).
    if run_since is not None and curr.last_seen_at is not None and curr.last_seen_at < run_since:
        return JobChangeVerdict(jid, ChangeType.REMOVED_FROM_SOURCE, ChangeSignificance.MEDIUM)
    # Source reported an update within the window.
    if (run_since is not None and curr.source_updated_at is not None
            and curr.source_updated_at >= run_since):
        return JobChangeVerdict(jid, ChangeType.UPDATED, ChangeSignificance.MEDIUM)
    if is_stale:
        return JobChangeVerdict(jid, ChangeType.STALE, ChangeSignificance.MEDIUM)
    return JobChangeVerdict(jid, ChangeType.UNCHANGED, ChangeSignificance.LOW)


def _build_events(
    verdict: JobChangeVerdict, curr: JobSnapshot, scheduler_run_id: int | None,
    existing: set[str], provenance: DataProvenance,
) -> list[JobChangeEvent]:
    out: list[JobChangeEvent] = []
    if verdict.change_type is ChangeType.UPDATED and verdict.field_changes:
        for fc in verdict.field_changes:
            key = _dedup_key(verdict, curr, fc.field_name)
            if key in existing:
                continue
            out.append(JobChangeEvent(
                canonical_job_id=verdict.canonical_job_id,
                company_id=curr.company_id,
                company_normalized_name=curr.company_normalized_name,
                change_type=verdict.change_type,
                field_name=fc.field_name,
                old_value=(fc.old_value or "")[:512] or None,
                new_value=(fc.new_value or "")[:512] or None,
                significance=fc.significance,
                scheduler_run_id=scheduler_run_id,
                dedup_key=key,
                data_provenance=provenance,
            ))
        return out
    key = _dedup_key(verdict, curr)
    if key in existing:
        return out
    out.append(JobChangeEvent(
        canonical_job_id=verdict.canonical_job_id,
        company_id=curr.company_id,
        company_normalized_name=curr.company_normalized_name,
        change_type=verdict.change_type,
        significance=verdict.significance,
        scheduler_run_id=scheduler_run_id,
        dedup_key=key,
        data_provenance=provenance,
    ))
    return out


def _bump(summary: JobChangeSummary, ct: ChangeType) -> None:
    mapping = {
        ChangeType.NEW: "new", ChangeType.UPDATED: "updated", ChangeType.CLOSED: "closed",
        ChangeType.REMOVED_FROM_SOURCE: "removed", ChangeType.REOPENED: "reopened",
        ChangeType.STALE: "stale", ChangeType.CONTRADICTED: "contradicted",
    }
    attr = mapping.get(ct)
    if attr:
        setattr(summary, attr, getattr(summary, attr) + 1)
