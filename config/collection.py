"""Collection-layer configuration: source priority/confidence, daily-run knobs,
and data-quality weights. Configurable so tuning never touches pipeline code.
"""

from __future__ import annotations

from dataclasses import dataclass, field

# Lower number = higher priority (canonical-source preference, §35). Official
# company career pages outrank third-party aggregators.
SOURCE_PRIORITY: dict[str, int] = {
    "company_career_pages": 1,
    "company_career": 1,
    "demo_career": 1,
    "adzuna": 2,
    "demo_jobs": 3,
}
DEFAULT_SOURCE_PRIORITY = 5

# Per-source evidence confidence (0-100). NOT a lead score — reliability of the
# source, used by the evidence layer.
SOURCE_CONFIDENCE: dict[str, int] = {
    "company_career_pages": 90,
    "company_career": 90,
    "demo_career": 85,
    "adzuna": 70,
    "demo_jobs": 60,
}
DEFAULT_SOURCE_CONFIDENCE = 50


def source_priority(source_id: str) -> int:
    return SOURCE_PRIORITY.get(source_id, DEFAULT_SOURCE_PRIORITY)


def source_confidence(source_id: str) -> int:
    return SOURCE_CONFIDENCE.get(source_id, DEFAULT_SOURCE_CONFIDENCE)


@dataclass(frozen=True)
class DailyCollectionConfig:
    """Defaults for (future) scheduled daily collection. Scheduler not built yet."""

    lookback_days: int = 7
    max_pages: int = 5
    max_records: int = 200
    requests_per_minute: int = 20
    timeout_seconds: int = 15


DEFAULT_DAILY_COLLECTION = DailyCollectionConfig()


@dataclass(frozen=True)
class DataQualityWeights:
    """Presence weights for the 0-100 data_quality_score (independent of scoring)."""

    company: int = 20
    title: int = 20
    published_at: int = 15
    source_url: int = 10
    description: int = 10
    location: int = 10
    technologies: int = 10
    external_id: int = 5
    fields: tuple[str, ...] = field(
        default=("company", "title", "published_at", "source_url", "description", "location", "technologies", "external_id")
    )


DEFAULT_QUALITY_WEIGHTS = DataQualityWeights()
