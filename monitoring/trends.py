"""Deterministic trend & surge detection on REAL historical observations
(§12, §13, §14).

All counts come from real ``JobRecord`` observations (``first_seen_at`` marks
when a canonical job was really first observed). Trends require enough history
or return ``INSUFFICIENT_DATA`` — we never guess a direction from one data
point. A hiring/technology surge is reported as a *business signal only* (§13);
whether it is a commercial opportunity is decided by the existing opportunity
logic, not here.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from database.models import DataProvenance, JobRecord, JobStatus, TrendStatus
from monitoring.config import (
    DEFAULT_HIRING_SURGE,
    DEFAULT_TECH_SURGE,
    DEFAULT_TREND,
    SurgeConfig,
    TrendConfig,
)


@dataclass(frozen=True)
class TrendResult:
    status: TrendStatus
    current: int
    previous: int
    ratio: float | None   # current / previous, None when previous == 0
    observations: int      # total data points across both periods


def classify_trend(current: int, previous: int, *, config: TrendConfig = DEFAULT_TREND) -> TrendResult:
    """Pure trend classification (§12). Returns INSUFFICIENT_DATA when the two
    periods together hold fewer than ``min_observations`` real observations."""
    observations = current + previous
    if observations < config.min_observations:
        return TrendResult(TrendStatus.INSUFFICIENT_DATA, current, previous, None, observations)

    if previous == 0:
        # Growth from a zero baseline: rising only if there is real current volume.
        status = TrendStatus.RAPIDLY_INCREASING if current >= config.min_observations else TrendStatus.INCREASING
        return TrendResult(status, current, previous, None, observations)

    ratio = current / previous
    if ratio >= config.rapid_ratio:
        status = TrendStatus.RAPIDLY_INCREASING
    elif ratio >= config.increase_ratio:
        status = TrendStatus.INCREASING
    elif ratio <= config.rapid_decrease_ratio:
        status = TrendStatus.RAPIDLY_DECREASING
    elif ratio <= config.decrease_ratio:
        status = TrendStatus.DECREASING
    else:
        status = TrendStatus.STABLE
    return TrendResult(status, current, previous, round(ratio, 3), observations)


@dataclass(frozen=True)
class SurgeResult:
    is_surge: bool
    current: int
    previous: int
    ratio: float | None
    label: str            # e.g. "HIRING_SURGE" or "AWS_DEMAND_SURGE"
    detail: str


def evaluate_surge(
    current: int, previous: int, *, label: str, config: SurgeConfig = DEFAULT_HIRING_SURGE,
    subject: str = "hiring",
) -> SurgeResult:
    """Pure surge test (§13, §14). Requires BOTH a meaningful absolute delta and
    a ratio increase over a non-trivial baseline, so small numbers never trip it.
    Emits a *signal*, never a commercial conclusion."""
    delta = current - previous
    ratio = (current / previous) if previous > 0 else None
    meets_absolute = current >= config.min_current and delta >= config.min_absolute_delta
    if previous >= config.min_baseline_for_ratio and previous > 0:
        meets_ratio = ratio is not None and ratio >= config.min_ratio
    else:
        # Zero/near-zero baseline: rely on the absolute-volume gate only.
        meets_ratio = True
    is_surge = bool(meets_absolute and meets_ratio)
    detail = (f"{subject}: {previous} → {current} over {config.period_days}d "
              f"(delta {delta}, ratio {round(ratio, 2) if ratio else 'n/a'})")
    return SurgeResult(is_surge, current, previous, round(ratio, 3) if ratio else None, label, detail)


# --------------------------------------------------------------------------- #
# Real-data drivers (read-only aggregation over JobRecord observations).
# --------------------------------------------------------------------------- #
def _period_bounds(now: datetime, period_days: int) -> tuple[datetime, datetime, datetime]:
    """Return (previous_start, current_start, current_end=now)."""
    current_start = now - timedelta(days=period_days)
    previous_start = current_start - timedelta(days=period_days)
    return previous_start, current_start, now


def _company_jobs(session: Session, normalized_company_name: str) -> list[JobRecord]:
    return session.execute(
        select(JobRecord).where(
            JobRecord.normalized_company_name == normalized_company_name,
            JobRecord.data_provenance == DataProvenance.REAL,
        )
    ).scalars().all()


def hiring_trend_for_company(
    session: Session, normalized_company_name: str, *, now: datetime,
    config: TrendConfig = DEFAULT_TREND,
) -> TrendResult:
    """Active-job hiring trend from real ``first_seen_at`` observations (§12)."""
    prev_start, curr_start, curr_end = _period_bounds(now, config.period_days)
    jobs = _company_jobs(session, normalized_company_name)
    current = sum(1 for j in jobs if j.first_seen_at and curr_start <= j.first_seen_at <= curr_end)
    previous = sum(1 for j in jobs if j.first_seen_at and prev_start <= j.first_seen_at < curr_start)
    return classify_trend(current, previous, config=config)


def detect_hiring_surge_for_company(
    session: Session, normalized_company_name: str, *, now: datetime,
    config: SurgeConfig = DEFAULT_HIRING_SURGE,
) -> SurgeResult:
    """Real hiring-surge detection: new canonical jobs this period vs previous
    (§13). Thresholds are configurable; output is a business signal."""
    prev_start, curr_start, curr_end = _period_bounds(now, config.period_days)
    jobs = _company_jobs(session, normalized_company_name)
    current = sum(1 for j in jobs if j.first_seen_at and curr_start <= j.first_seen_at <= curr_end)
    previous = sum(1 for j in jobs if j.first_seen_at and prev_start <= j.first_seen_at < curr_start)
    return evaluate_surge(current, previous, label="HIRING_SURGE", config=config, subject="hiring")


def detect_technology_surges_for_company(
    session: Session, normalized_company_name: str, *, now: datetime,
    tracked: tuple[str, ...], config: SurgeConfig = DEFAULT_TECH_SURGE,
) -> list[SurgeResult]:
    """Per-technology demand surges from real canonical-job technologies (§14).
    Only tracked technologies are considered; demand is never invented."""
    prev_start, curr_start, curr_end = _period_bounds(now, config.period_days)
    jobs = _company_jobs(session, normalized_company_name)
    tracked_set = {t.lower() for t in tracked}
    current: Counter[str] = Counter()
    previous: Counter[str] = Counter()
    for j in jobs:
        if not j.first_seen_at:
            continue
        techs = {str(t).strip().lower() for t in (j.technologies or []) if str(t).strip()}
        techs &= tracked_set
        if curr_start <= j.first_seen_at <= curr_end:
            current.update(techs)
        elif prev_start <= j.first_seen_at < curr_start:
            previous.update(techs)

    results: list[SurgeResult] = []
    for tech in sorted(set(current) | set(previous)):
        label = f"{tech.upper().replace(' ', '_')}_DEMAND_SURGE"
        res = evaluate_surge(current[tech], previous[tech], label=label, config=config, subject=f"{tech} demand")
        if res.is_surge:
            results.append(res)
    return results
