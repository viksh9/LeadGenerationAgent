"""Configurable policies for the monitoring & scheduling layer (§4, §8, §13,
§14, §16, §28, §37).

Cadence, thresholds, and significance rules live here — NOT in business logic —
so tuning never touches the detection/scheduler code. Values are conservative
defaults; callers may pass a custom config to any engine for testing or tuning.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from database.models import JobType

# --------------------------------------------------------------------------- #
# Source / job-type schedules (§4). Interval seconds; fully configurable.
# These are seeds for ScheduledJob rows, not hard limits — a persisted job's
# own ``interval_seconds`` always wins once created.
# --------------------------------------------------------------------------- #
MINUTE = 60
HOUR = 60 * MINUTE
DAY = 24 * HOUR

# Per-source-category collection cadence.
DEFAULT_SOURCE_INTERVALS: dict[str, int] = {
    "jobs": 6 * HOUR,        # frequent enough to detect new hiring
    "tenders": 6 * HOUR,     # catch newly published opportunities / deadlines
    "news": 12 * HOUR,       # official announcements
    "business": 12 * HOUR,
    "default": 12 * HOUR,
}

# Per-job-type cadence for non-collection maintenance jobs.
DEFAULT_JOB_INTERVALS: dict[JobType, int] = {
    JobType.SOURCE_COLLECTION: 6 * HOUR,
    JobType.EVIDENCE_REVERIFICATION: DAY,
    JobType.COMPANY_ENRICHMENT: DAY,
    JobType.SIGNAL_RECOMPUTATION: 12 * HOUR,
    JobType.OPPORTUNITY_RECOMPUTATION: 12 * HOUR,
    JobType.AI_REANALYSIS: DAY,          # event/change-driven, not every refresh
    JobType.NOTIFICATION_DISPATCH: 15 * MINUTE,
    JobType.SOURCE_HEALTH_CHECK: 6 * HOUR,
    JobType.TENDER_DEADLINE_SCAN: 6 * HOUR,
}


@dataclass(frozen=True)
class SurgeConfig:
    """Hiring / technology surge thresholds (§13, §14).

    A surge requires BOTH a meaningful absolute increase and a ratio increase
    over a non-trivial baseline, so tiny numbers (1 -> 3) never trigger. A surge
    is emitted as a *business signal*; commercial interpretation is left to the
    existing opportunity logic (§13).
    """

    min_current: int = 6           # need at least this many in the current period
    min_absolute_delta: int = 5    # current - previous must be >= this
    min_ratio: float = 2.0         # current / max(previous, 1) must be >= this
    min_baseline_for_ratio: int = 1
    period_days: int = 30          # comparison window length


DEFAULT_HIRING_SURGE = SurgeConfig()
DEFAULT_TECH_SURGE = SurgeConfig(min_current=5, min_absolute_delta=4, min_ratio=2.0)

# Technologies we track for demand surges (§14). Real canonical-job technologies
# only; this is a normalization vocabulary, not invented demand.
TRACKED_TECHNOLOGIES: tuple[str, ...] = (
    "java", "python", "javascript", "typescript", "react", "angular", "node",
    "aws", "azure", "gcp", "cloud", "devops", "kubernetes", "docker",
    "ai", "ml", "machine learning", "data engineering", "data science",
    "cybersecurity", "security", ".net", "golang", "salesforce", "sap",
)


@dataclass(frozen=True)
class TrendConfig:
    """Deterministic trend classification (§12). Needs enough real observations;
    otherwise returns INSUFFICIENT_DATA rather than guessing."""

    min_observations: int = 3          # across the two compared periods
    rapid_ratio: float = 2.0
    increase_ratio: float = 1.25
    decrease_ratio: float = 0.8
    rapid_decrease_ratio: float = 0.5
    period_days: int = 30


DEFAULT_TREND = TrendConfig()


@dataclass(frozen=True)
class TenderMonitorConfig:
    """Tender deadline monitoring (§16, §17)."""

    closing_soon_days: int = 7         # alert window before closing_date
    # Statuses considered "still open" for CLOSING_SOON eligibility.
    open_statuses: tuple[str, ...] = ("OPEN", "CLOSING_SOON", "UNKNOWN")


DEFAULT_TENDER_MONITOR = TenderMonitorConfig()


@dataclass(frozen=True)
class SourceHealthConfig:
    """Source-health monitoring thresholds (§19, §20)."""

    failure_alert_after: int = 1       # consecutive failures before a failure event
    # Rate-limit / auth failures are always significant (single occurrence).


DEFAULT_SOURCE_HEALTH = SourceHealthConfig()


@dataclass(frozen=True)
class LeadChangeConfig:
    """Lead-change significance thresholds (§10)."""

    min_score_delta: int = 5           # ignore score jitter below this
    strong_score_delta: int = 15       # HIGH significance above this


DEFAULT_LEAD_CHANGE = LeadChangeConfig()


@dataclass(frozen=True)
class AlertConfig:
    """Alert deduplication + severity policy (§28, §29)."""

    dedup_window_hours: int = 24       # re-alert only after this unless state changes
    # Conservative default set of enabled alert types (§32) — high-value only.
    default_enabled_types: tuple[str, ...] = (
        "NEW_HIGH_INTENT_LEAD", "LEAD_PRIORITY_INCREASED", "HIRING_SURGE",
        "NEW_PROJECT", "NEW_TENDER", "TENDER_CLOSING_SOON",
        "EVIDENCE_CONFLICT", "SOURCE_FAILURE", "SOURCE_RECOVERED",
    )


DEFAULT_ALERT = AlertConfig()


@dataclass(frozen=True)
class MonitoringConfig:
    """Umbrella config bundling every tunable policy."""

    hiring_surge: SurgeConfig = DEFAULT_HIRING_SURGE
    tech_surge: SurgeConfig = DEFAULT_TECH_SURGE
    trend: TrendConfig = DEFAULT_TREND
    tender: TenderMonitorConfig = DEFAULT_TENDER_MONITOR
    source_health: SourceHealthConfig = DEFAULT_SOURCE_HEALTH
    lead_change: LeadChangeConfig = DEFAULT_LEAD_CHANGE
    alert: AlertConfig = DEFAULT_ALERT
    tracked_technologies: tuple[str, ...] = TRACKED_TECHNOLOGIES


DEFAULT_MONITORING = MonitoringConfig()
