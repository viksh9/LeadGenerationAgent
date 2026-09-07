"""Configuration for cross-source job deduplication (weights + thresholds).

All tuning lives here so matching logic stays stable. Scores are 0-100.
"""

from __future__ import annotations

from dataclasses import dataclass

DEDUPLICATION_VERSION = "1.0.0"


@dataclass(frozen=True)
class DedupConfig:
    # Strong exact signals.
    score_same_source_external_id: int = 100
    score_same_url: int = 95

    # Composite component weights (company match is required for any match).
    weight_company_domain: int = 40
    weight_company_name: int = 34
    weight_title_exact: int = 30
    weight_title_similar: int = 20     # * title token similarity
    weight_location_city: int = 20
    weight_location_state: int = 10
    weight_remote_match: int = 16
    weight_date_close: int = 6         # within date_close_days
    weight_date_near: int = 3          # within date_near_days
    weight_description: int = 20       # * description similarity

    date_close_days: int = 3
    date_near_days: int = 14

    # Decision thresholds (configurable).
    auto_merge_min: int = 85
    review_min: int = 62

    # Guards against over-merging distinct jobs (§7, §39).
    title_similar_min: float = 0.80    # below this, titles are considered different
    description_similar_strong: float = 0.72  # needed to merge when titles are not exact

    # Recency windows for canonical hiring counts (days).
    very_recent_days: int = 7
    recent_days: int = 30
    old_days: int = 90


DEFAULT_DEDUP_CONFIG = DedupConfig()
