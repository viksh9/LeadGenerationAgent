"""SchedulerService — deterministic, in-process scheduling over the pipeline.

Responsibilities:
* seed/register recurring jobs (idempotent by ``job_name``);
* decide which jobs are due (``due_jobs``) using an injected ``now``;
* run one job with idempotency, per-source locking, retry policy, and a full
  ``SchedulerRun`` audit row (§21–§24, §41);
* pause / resume / enable / disable jobs.

Everything is clock-injectable and free of ambient time/network in its core, so
it is fully unit-testable. The only time source is the ``now`` argument.
"""

from __future__ import annotations

import logging
import threading
from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from database.models import (
    JobType,
    ScheduledJob,
    ScheduledJobStatus,
    SchedulerRun,
    SchedulerRunStatus,
    utcnow,
)
from monitoring.config import DEFAULT_JOB_INTERVALS, DEFAULT_SOURCE_INTERVALS
from scheduler.errors import PermanentJobError, SkipJob, TransientJobError
from scheduler.handlers import get_handler

logger = logging.getLogger(__name__)

# Process-wide locks preventing the same source/job running concurrently (§22).
# Shared across the API thread and the background runner thread.
_LOCKS: dict[str, threading.Lock] = {}
_LOCKS_GUARD = threading.Lock()

_RUN_COUNTERS = (
    "records_fetched", "records_new", "records_changed", "records_unchanged",
    "records_removed", "signals_changed", "opportunities_changed", "leads_changed",
    "alerts_generated",
)


def _lock_for(key: str) -> threading.Lock:
    with _LOCKS_GUARD:
        lock = _LOCKS.get(key)
        if lock is None:
            lock = threading.Lock()
            _LOCKS[key] = lock
        return lock


def _safe_error(exc: Exception, limit: int = 500) -> str:
    """Credential-free, length-capped error string (§44 — never leak secrets)."""
    msg = f"{type(exc).__name__}: {exc}"
    return msg[:limit]


class SchedulerService:
    def __init__(self, session: Session):
        self.session = session

    # ------------------------------------------------------------------ #
    # Seeding / registration
    # ------------------------------------------------------------------ #
    def seed_default_jobs(self, *, now: datetime | None = None) -> list[ScheduledJob]:
        """Create the default recurring jobs if missing (idempotent). Source
        collection jobs are seeded from the runnable-source registry."""
        now = now or utcnow()
        created: list[ScheduledJob] = []

        # One collection job per runnable source.
        try:
            from collectors.registry import runnable_source_ids
            from collectors.source_registry import get_registry
            registry = get_registry()
            for source_id in sorted(runnable_source_ids()):
                defn = registry.get(source_id)
                category = getattr(getattr(defn, "category", None), "value", None) or "default"
                interval = DEFAULT_SOURCE_INTERVALS.get(category, DEFAULT_SOURCE_INTERVALS["default"])
                job = self.register_job(
                    job_name=f"collect:{source_id}", job_type=JobType.SOURCE_COLLECTION,
                    interval_seconds=interval, source_id=source_id, now=now,
                    # Sources are enabled for scheduling but only collect when
                    # actually configured (handler raises SkipJob otherwise).
                    enabled=True,
                )
                if job is not None:
                    created.append(job)
        except Exception:  # registry issues must not block maintenance jobs
            logger.warning("could not seed source-collection jobs", exc_info=True)

        # Maintenance jobs.
        maintenance = [
            ("monitoring:notify", JobType.NOTIFICATION_DISPATCH),
            ("reverify:evidence", JobType.EVIDENCE_REVERIFICATION),
            ("recompute:signals", JobType.SIGNAL_RECOMPUTATION),
            ("recompute:opportunities", JobType.OPPORTUNITY_RECOMPUTATION),
            ("ai:reanalyze", JobType.AI_REANALYSIS),
            ("health:sources", JobType.SOURCE_HEALTH_CHECK),
            ("tenders:deadlines", JobType.TENDER_DEADLINE_SCAN),
        ]
        for name, jtype in maintenance:
            interval = DEFAULT_JOB_INTERVALS.get(jtype, 12 * 3600)
            job = self.register_job(job_name=name, job_type=jtype, interval_seconds=interval, now=now)
            if job is not None:
                created.append(job)

        self.session.flush()
        return created

    def register_job(
        self, *, job_name: str, job_type: JobType, interval_seconds: int,
        source_id: str | None = None, enabled: bool = True, config: dict | None = None,
        now: datetime | None = None,
    ) -> ScheduledJob | None:
        """Create a job if it does not exist. Returns the new job, or None if it
        already existed (idempotent)."""
        now = now or utcnow()
        existing = self.get_by_name(job_name)
        if existing is not None:
            return None
        job = ScheduledJob(
            job_name=job_name, job_type=job_type, enabled=enabled,
            interval_seconds=interval_seconds, source_id=source_id,
            config=config or {}, schedule=_human_interval(interval_seconds),
            next_run_at=now, current_status=ScheduledJobStatus.SCHEDULED if enabled
            else ScheduledJobStatus.DISABLED,
        )
        self.session.add(job)
        self.session.flush()
        return job

    # ------------------------------------------------------------------ #
    # Queries
    # ------------------------------------------------------------------ #
    def get(self, job_id: int) -> ScheduledJob | None:
        return self.session.get(ScheduledJob, job_id)

    def get_by_name(self, job_name: str) -> ScheduledJob | None:
        return self.session.execute(
            select(ScheduledJob).where(ScheduledJob.job_name == job_name)
        ).scalars().first()

    def list_jobs(self) -> list[ScheduledJob]:
        return list(self.session.execute(
            select(ScheduledJob).order_by(ScheduledJob.job_name)
        ).scalars().all())

    def due_jobs(self, now: datetime) -> list[ScheduledJob]:
        """Enabled, non-paused, not-currently-running jobs whose next_run_at has
        arrived (or is unset)."""
        jobs = self.session.execute(
            select(ScheduledJob).where(ScheduledJob.enabled.is_(True))
        ).scalars().all()
        due = []
        for job in jobs:
            if job.current_status in (ScheduledJobStatus.RUNNING, ScheduledJobStatus.PAUSED,
                                      ScheduledJobStatus.DISABLED):
                continue
            if job.next_run_at is None or job.next_run_at <= now:
                due.append(job)
        return due

    # ------------------------------------------------------------------ #
    # Lifecycle controls
    # ------------------------------------------------------------------ #
    def pause(self, job_id: int) -> ScheduledJob | None:
        return self._set_enabled(job_id, enabled=False, status=ScheduledJobStatus.PAUSED)

    def resume(self, job_id: int, *, now: datetime | None = None) -> ScheduledJob | None:
        job = self.get(job_id)
        if job is None:
            return None
        job.enabled = True
        job.current_status = ScheduledJobStatus.SCHEDULED
        job.next_run_at = now or utcnow()
        self.session.flush()
        return job

    def set_enabled(self, job_id: int, enabled: bool) -> ScheduledJob | None:
        return self._set_enabled(
            job_id, enabled=enabled,
            status=ScheduledJobStatus.SCHEDULED if enabled else ScheduledJobStatus.DISABLED,
        )

    def _set_enabled(self, job_id: int, *, enabled: bool, status: ScheduledJobStatus) -> ScheduledJob | None:
        job = self.get(job_id)
        if job is None:
            return None
        job.enabled = enabled
        job.current_status = status
        self.session.flush()
        return job

    # ------------------------------------------------------------------ #
    # Execution
    # ------------------------------------------------------------------ #
    def _bucket(self, job: ScheduledJob, now: datetime) -> int:
        interval = max(1, job.interval_seconds)
        return int(now.timestamp()) // interval

    def _run_exists(self, run_key: str) -> bool:
        return self.session.execute(
            select(SchedulerRun.id).where(SchedulerRun.run_key == run_key)
        ).scalars().first() is not None

    def run_job(self, job: ScheduledJob, *, now: datetime | None = None, trigger: str = "SCHEDULE") -> SchedulerRun:
        """Run one job with idempotency, locking, retry policy, and full audit."""
        now = now or utcnow()

        # Idempotency (§21): a scheduled run for the same interval bucket runs once.
        if trigger == "SCHEDULE":
            run_key = f"{job.job_name}:SCHEDULE:{self._bucket(job, now)}"
        else:
            run_key = f"{job.job_name}:{trigger}:{now.isoformat()}"
        if trigger == "SCHEDULE" and self._run_exists(run_key):
            return self._skip_run(job, run_key, now, trigger, "duplicate scheduled run suppressed")

        # Locking (§22): don't collect the same source concurrently.
        lock_key = f"source:{job.source_id}" if job.source_id else f"job:{job.job_name}"
        lock = _lock_for(lock_key)
        if not lock.acquire(blocking=False):
            return self._skip_run(job, run_key, now, trigger, "another run holds the lock")

        run = SchedulerRun(
            job_id=job.id, job_name=job.job_name, job_type=job.job_type,
            source_id=job.source_id, run_key=run_key, trigger=trigger,
            started_at=now, status=SchedulerRunStatus.RUNNING,
        )
        self.session.add(run)
        job.current_status = ScheduledJobStatus.RUNNING
        job.last_run_at = now
        self.session.flush()

        try:
            handler = get_handler(job.job_type)
            stats = handler(self.session, job, now) or {}
            self._apply_stats(run, stats)
            run.status = SchedulerRunStatus.SUCCESS
            job.current_status = ScheduledJobStatus.SUCCESS
            job.last_success_at = now
            job.consecutive_failures = 0
            job.last_error = None
            job.next_run_at = now + timedelta(seconds=job.interval_seconds)
        except SkipJob as exc:
            run.status = SchedulerRunStatus.SKIPPED
            run.error = _safe_error(exc)
            job.current_status = ScheduledJobStatus.SCHEDULED
            job.next_run_at = now + timedelta(seconds=job.interval_seconds)
        except PermanentJobError as exc:
            self._record_failure(job, run, exc, now, retry=False)
        except (TransientJobError, Exception) as exc:  # noqa: BLE001 - all else is transient
            self._record_failure(job, run, exc, now, retry=True)
        finally:
            lock.release()
            finished = now
            run.finished_at = finished
            run.duration_seconds = max(0.0, (finished - run.started_at).total_seconds())
            self.session.flush()

        return run

    def _record_failure(self, job: ScheduledJob, run: SchedulerRun, exc: Exception,
                        now: datetime, *, retry: bool) -> None:
        run.status = SchedulerRunStatus.FAILED
        run.error = _safe_error(exc)
        job.current_status = ScheduledJobStatus.FAILED
        job.last_failure_at = now
        job.last_error = _safe_error(exc)
        job.consecutive_failures = (job.consecutive_failures or 0) + 1
        # Retry policy (§23): transient failures back off and retry until
        # max_retries; permanent failures wait for the normal interval.
        if retry and job.consecutive_failures <= job.max_retries:
            run.retry_count = job.consecutive_failures
            job.next_run_at = now + timedelta(seconds=job.retry_backoff_seconds)
        else:
            job.next_run_at = now + timedelta(seconds=job.interval_seconds)

    def _skip_run(self, job: ScheduledJob, run_key: str, now: datetime, trigger: str, reason: str) -> SchedulerRun:
        run = SchedulerRun(
            job_id=job.id, job_name=job.job_name, job_type=job.job_type, source_id=job.source_id,
            run_key=f"{run_key}:skip:{now.timestamp()}", trigger=trigger, started_at=now,
            finished_at=now, duration_seconds=0.0, status=SchedulerRunStatus.SKIPPED, error=reason,
        )
        self.session.add(run)
        self.session.flush()
        return run

    def _apply_stats(self, run: SchedulerRun, stats: dict) -> None:
        for key in _RUN_COUNTERS:
            if key in stats and stats[key] is not None:
                setattr(run, key, int(stats[key]))
        notes = {k: v for k, v in stats.items() if k not in _RUN_COUNTERS}
        if notes:
            run.notes = notes
        if stats.get("errors"):
            run.status = SchedulerRunStatus.PARTIAL

    # ------------------------------------------------------------------ #
    # Tick: run all due jobs (used by the background runner and tests).
    # ------------------------------------------------------------------ #
    def tick(self, *, now: datetime | None = None) -> list[SchedulerRun]:
        now = now or utcnow()
        runs = []
        for job in self.due_jobs(now):
            runs.append(self.run_job(job, now=now, trigger="SCHEDULE"))
        return runs


def _human_interval(seconds: int) -> str:
    if seconds % 86400 == 0:
        return f"every {seconds // 86400}d"
    if seconds % 3600 == 0:
        return f"every {seconds // 3600}h"
    if seconds % 60 == 0:
        return f"every {seconds // 60}m"
    return f"every {seconds}s"
