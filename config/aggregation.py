"""Configuration for company-level job aggregation and hiring intensity.

All thresholds are configurable here rather than hard-coded in the engine, so the
Indian IT-market tuning can evolve without touching aggregation logic.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class AggregationConfig:
    # Recency windows (days) used for freshness and "recent hiring" counts.
    recent_days: int = 30
    fresh_windows: tuple[int, ...] = (7, 14, 30)

    # A job older than this contributes little as a *new* hiring signal.
    stale_days: int = 180

    # Hiring-intensity thresholds by active IT job count (lower bound inclusive).
    # Example: 3 -> LOW, 10 -> MEDIUM, 25 -> HIGH, 50+ -> VERY_HIGH.
    intensity_medium: int = 10
    intensity_high: int = 25
    intensity_very_high: int = 50

    # Company-signal thresholds.
    large_hiring_min: int = 25          # LARGE_TECH_HIRING
    multi_tech_min: int = 3             # MULTI_TECH_HIRING (distinct tech categories)
    multi_city_min: int = 2             # ENGINEERING_EXPANSION (distinct cities)
    rapid_hiring_recent_ratio: float = 0.5  # >=50% of jobs posted within recent_days
    rapid_hiring_min_recent: int = 5    # and at least this many recent jobs

    # A company must have at least this many IT jobs to become a lead at all.
    min_jobs_for_lead: int = 1

    # Company-opportunity scoring weights (max ~100 before clamp).
    weight_intensity: dict[str, int] = field(
        default_factory=lambda: {"LOW": 10, "MEDIUM": 30, "HIGH": 50, "VERY_HIGH": 65}
    )
    weight_recent_ratio: int = 15       # * share of recent jobs
    weight_tech_breadth: int = 4        # * distinct tech categories (capped)
    weight_tech_breadth_cap: int = 20
    weight_per_signal: int = 6          # * number of company signals (capped)
    weight_signal_cap: int = 18
    weight_multi_source: int = 6        # bonus when >1 independent source
    weight_seniority: int = 8           # bonus when senior/lead/architect roles present

    # Priority thresholds (aligned with the lead scorer: HOT>=80, WARM>=60,
    # NURTURE>=40, else LOW).
    hot_threshold: int = 80
    warm_threshold: int = 60
    nurture_threshold: int = 40


DEFAULT_AGGREGATION_CONFIG = AggregationConfig()
