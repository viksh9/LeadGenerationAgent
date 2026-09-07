"""Configuration for evidence verification (tiers, freshness, corroboration,
thresholds). All business assumptions live here so verification LOGIC never has
to be rewritten to re-tune. Deterministic — no LLM.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from database.models import BusinessSignalType, SourceTier, VerificationStatus

VERIFICATION_VERSION = "1.0.0"
VERIFIER_RULES_VERSION = "1.0.0"

# --- Source trust tiers (configurable) ------------------------------------- #
SOURCE_TIER_BY_ID: dict[str, SourceTier] = {
    "company_career_pages": SourceTier.TIER_1,
    "company_career": SourceTier.TIER_1,
    "company_newsroom": SourceTier.TIER_1,
    "government_open_data": SourceTier.TIER_1,
    "government_procurement": SourceTier.TIER_1,
    "demo_career": SourceTier.TIER_1,
    "adzuna": SourceTier.TIER_2,          # licensed aggregator / official API
    "stock_exchange_announcements": SourceTier.TIER_2,
    "business_news": SourceTier.TIER_2,
    "rss_news": SourceTier.TIER_3,
    "demo_jobs": SourceTier.TIER_3,
    "demo_business": SourceTier.TIER_3,
}
SOURCE_TIER_BY_CATEGORY: dict[str, SourceTier] = {
    "COMPANY": SourceTier.TIER_1,
    "GOVERNMENT": SourceTier.TIER_1,
    "TENDER": SourceTier.TIER_1,
    "JOB": SourceTier.TIER_2,
    "NEWS": SourceTier.TIER_3,
    "PROJECT": SourceTier.TIER_3,
    "BUSINESS_DATABASE": SourceTier.TIER_2,
}
DEFAULT_TIER = SourceTier.TIER_4

# Base scores per tier (0-100). reliability != authority.
TIER_RELIABILITY: dict[SourceTier, int] = {
    SourceTier.TIER_1: 92, SourceTier.TIER_2: 72, SourceTier.TIER_3: 45, SourceTier.TIER_4: 22,
}
TIER_AUTHORITY: dict[SourceTier, int] = {
    SourceTier.TIER_1: 95, SourceTier.TIER_2: 70, SourceTier.TIER_3: 40, SourceTier.TIER_4: 20,
}
# Tiers considered "official/authoritative" for corroboration independence.
AUTHORITATIVE_TIERS = frozenset({SourceTier.TIER_1, SourceTier.TIER_2})


@dataclass(frozen=True)
class FreshnessPolicy:
    """Per-signal-type freshness windows in days (configurable, not universal)."""

    very_recent_days: int = 7
    recent_days: int = 30
    stale_after_days: int = 90
    # If the source explicitly says the role/tender is still active, freshness is
    # not decayed below this floor even when old.
    active_floor: int = 55


# Keyed by BusinessSignalType.value (job hiring maps via "HIRING").
FRESHNESS_POLICIES: dict[str, FreshnessPolicy] = {
    "HIRING": FreshnessPolicy(7, 30, 90, 55),
    "PROJECT_AWARD": FreshnessPolicy(14, 60, 180, 60),
    "PROJECT_EXECUTION": FreshnessPolicy(30, 120, 365, 60),
    "CONTRACT": FreshnessPolicy(14, 60, 180, 60),
    "TENDER": FreshnessPolicy(7, 30, 60, 50),      # expired tender = stale
    "DIGITAL_TRANSFORMATION": FreshnessPolicy(30, 120, 365, 55),
    "CLOUD_MIGRATION": FreshnessPolicy(30, 120, 365, 55),
    "AI_INITIATIVE": FreshnessPolicy(30, 120, 365, 55),
    "EXPANSION": FreshnessPolicy(30, 90, 270, 50),
    "DELIVERY_CENTER_EXPANSION": FreshnessPolicy(30, 120, 365, 55),
    "ENGINEERING_EXPANSION": FreshnessPolicy(14, 60, 180, 55),
    "VENDOR_REQUIREMENT": FreshnessPolicy(7, 30, 60, 50),
    "OUTSOURCING": FreshnessPolicy(14, 60, 180, 55),
    "PARTNERSHIP": FreshnessPolicy(30, 120, 365, 50),
    "ACQUISITION": FreshnessPolicy(60, 180, 540, 50),
}
DEFAULT_FRESHNESS = FreshnessPolicy()


def freshness_policy_for(signal_type: str | None) -> FreshnessPolicy:
    return FRESHNESS_POLICIES.get(signal_type or "", DEFAULT_FRESHNESS)


# --- Corroboration weights -------------------------------------------------- #
# Independent supporting sources add corroboration; syndicated copies do not.
CORROBORATION_PER_INDEPENDENT = 22      # per independent source beyond the first
CORROBORATION_OFFICIAL_BONUS = 12       # an official (TIER_1) source among them
CORROBORATION_CAP = 60


@dataclass(frozen=True)
class VerificationThresholds:
    verified_min_confidence: int = 70
    verified_min_freshness: int = 50
    partial_min_confidence: int = 45
    stale_max_freshness: int = 25       # below this + old -> STALE
    # Lead readiness (evidence-based, NOT the commercial lead score).
    ready_min_confidence: int = 68
    ready_min_freshness: int = 50
    review_min_confidence: int = 40


DEFAULT_THRESHOLDS = VerificationThresholds()

# Status ranking for "best" selection.
STATUS_RANK: dict[VerificationStatus, int] = {
    VerificationStatus.VERIFIED: 4,
    VerificationStatus.PARTIALLY_VERIFIED: 3,
    VerificationStatus.STALE: 2,
    VerificationStatus.UNVERIFIED: 1,
    VerificationStatus.CONTRADICTED: 0,
}
