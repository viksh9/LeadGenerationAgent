"""Cross-source corroboration + independence grouping.

The same job on 10 sites is NOT 10 confirmations. Syndicated copies of the same
underlying evidence (same canonical job or same content hash) are grouped into
ONE EvidenceIndependenceGroup; only DISTINCT groups count as independent support.
Reuses the canonical-job identity from the deduplication stage.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from typing import Optional

from config.evidence import (
    AUTHORITATIVE_TIERS,
    CORROBORATION_CAP,
    CORROBORATION_OFFICIAL_BONUS,
    CORROBORATION_PER_INDEPENDENT,
)
from database.models import SourceTier


@dataclass
class EvidenceItem:
    source_id: str
    source_tier: SourceTier
    content_hash: Optional[str] = None
    canonical_job_id: Optional[int] = None
    source_url: Optional[str] = None


@dataclass
class IndependenceGroup:
    group_id: str
    source_ids: set = field(default_factory=set)
    tiers: set = field(default_factory=set)
    urls: set = field(default_factory=set)

    @property
    def is_official(self) -> bool:
        return any(t in AUTHORITATIVE_TIERS for t in self.tiers)


@dataclass
class CorroborationResult:
    independent_support_count: int
    syndicated_count: int
    corroboration_score: int
    groups: list[IndependenceGroup]


def _group_key(item: EvidenceItem) -> str:
    if item.canonical_job_id is not None:
        return f"job:{item.canonical_job_id}"
    if item.content_hash:
        return f"hash:{item.content_hash}"
    # No shared identity → treat as its own group, keyed by source+url.
    return f"src:{item.source_id}:{item.source_url or ''}"


def group_evidence(items: list[EvidenceItem]) -> list[IndependenceGroup]:
    """Group syndicated copies of the same underlying evidence together."""
    groups: dict[str, IndependenceGroup] = {}
    for it in items:
        key = _group_key(it)
        gid = hashlib.sha256(key.encode("utf-8")).hexdigest()[:16]
        g = groups.setdefault(gid, IndependenceGroup(group_id=gid))
        g.source_ids.add(it.source_id)
        g.tiers.add(it.source_tier)
        if it.source_url:
            g.urls.add(it.source_url)
    return list(groups.values())


def corroborate(items: list[EvidenceItem]) -> CorroborationResult:
    groups = group_evidence(items)
    independent = len(groups)
    total_refs = len(items)
    syndicated = max(0, total_refs - independent)   # extra copies of same evidence
    score = (independent - 1) * CORROBORATION_PER_INDEPENDENT if independent > 1 else 0
    if any(g.is_official for g in groups) and independent > 1:
        score += CORROBORATION_OFFICIAL_BONUS
    score = max(0, min(CORROBORATION_CAP, score))
    return CorroborationResult(
        independent_support_count=independent,
        syndicated_count=syndicated,
        corroboration_score=score,
        groups=groups,
    )
