"""Deterministic Source Reliability Engine.

How trustworthy is the SOURCE itself — independent of any specific claim. This is
NOT evidence confidence and NOT the lead score. No LLM.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from config.evidence import (
    DEFAULT_TIER,
    SOURCE_TIER_BY_CATEGORY,
    SOURCE_TIER_BY_ID,
    TIER_AUTHORITY,
    TIER_RELIABILITY,
    VERIFIER_RULES_VERSION,
)
from database.models import SourceTier


def source_tier_for(source_id: Optional[str], category: Optional[str] = None) -> SourceTier:
    if source_id and source_id in SOURCE_TIER_BY_ID:
        return SOURCE_TIER_BY_ID[source_id]
    if category and category.upper() in SOURCE_TIER_BY_CATEGORY:
        return SOURCE_TIER_BY_CATEGORY[category.upper()]
    return DEFAULT_TIER


@dataclass
class SourceReliabilityResult:
    source_name: Optional[str]
    source_tier: SourceTier
    reliability_score: int
    authority_score: int
    freshness_capability: int      # how well the source exposes reliable dates/status
    provenance_quality: int        # how clean/traceable its provenance is
    reliability_reasons: list[str] = field(default_factory=list)
    confidence: int = 0            # confidence in this reliability assessment itself
    rules_version: str = VERIFIER_RULES_VERSION


# Sources that expose reliable structured dates / status get higher freshness
# capability; official first-party sources have the best provenance.
_HIGH_FRESHNESS_TIERS = {SourceTier.TIER_1, SourceTier.TIER_2}


def compute_source_reliability(
    source_id: Optional[str], *, category: Optional[str] = None, source_name: Optional[str] = None
) -> SourceReliabilityResult:
    tier = source_tier_for(source_id, category)
    reliability = TIER_RELIABILITY[tier]
    authority = TIER_AUTHORITY[tier]
    freshness_cap = 85 if tier in _HIGH_FRESHNESS_TIERS else 55
    provenance = 90 if tier is SourceTier.TIER_1 else (70 if tier is SourceTier.TIER_2 else 40)
    reasons = [f"Source tier {tier.value} (reliability {reliability}, authority {authority})."]
    if source_id and source_id in SOURCE_TIER_BY_ID:
        reasons.append(f"Configured tier for source '{source_id}'.")
    elif category:
        reasons.append(f"Tier derived from source category '{category}'.")
    else:
        reasons.append("Unknown source — lowest tier assumed.")
    # Confidence in the assessment: high when the source is explicitly configured.
    assessment_conf = 90 if (source_id and source_id in SOURCE_TIER_BY_ID) else (65 if category else 40)
    return SourceReliabilityResult(
        source_name=source_name or source_id,
        source_tier=tier,
        reliability_score=reliability,
        authority_score=authority,
        freshness_capability=freshness_cap,
        provenance_quality=provenance,
        reliability_reasons=reasons,
        confidence=assessment_conf,
    )
