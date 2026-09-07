"""Deterministic conflict detection between pieces of evidence.

Contradictory evidence is never silently discarded — a conflict is recorded and
the stronger/authoritative evidence is preferred via explicit rules.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Optional

from database.models import ConflictSeverity, ConflictType, SourceTier

_TIER_ORDER = {SourceTier.TIER_1: 1, SourceTier.TIER_2: 2, SourceTier.TIER_3: 3, SourceTier.TIER_4: 4}
_EXPIRED = {"expired", "closed", "filled", "cancelled", "inactive"}
_ACTIVE = {"active", "open", "live"}


@dataclass
class ConflictEvidence:
    index: int
    source_id: str
    source_tier: SourceTier
    normalized_company_name: Optional[str] = None
    normalized_title: Optional[str] = None
    city: Optional[str] = None
    status: Optional[str] = None            # job/tender status
    project_status: Optional[str] = None
    published_at: Optional[datetime] = None


@dataclass
class ConflictFinding:
    conflict_type: ConflictType
    severity: ConflictSeverity
    description: str
    index_a: int
    index_b: int
    preferred_index: int


def _preferred(a: ConflictEvidence, b: ConflictEvidence) -> int:
    """The more authoritative source wins (lower tier order)."""
    return a.index if _TIER_ORDER[a.source_tier] <= _TIER_ORDER[b.source_tier] else b.index


def _status_class(s: Optional[str]) -> Optional[str]:
    if not s:
        return None
    low = s.lower()
    if low in _EXPIRED:
        return "expired"
    if low in _ACTIVE:
        return "active"
    return None


def detect_conflicts(items: list[ConflictEvidence]) -> list[ConflictFinding]:
    findings: list[ConflictFinding] = []
    for i in range(len(items)):
        for j in range(i + 1, len(items)):
            a, b = items[i], items[j]
            # Job/tender status: active vs expired.
            sa, sb = _status_class(a.status), _status_class(b.status)
            if sa and sb and sa != sb:
                findings.append(ConflictFinding(
                    ConflictType.JOB_STATUS, ConflictSeverity.HIGH,
                    f"Status conflict: {a.source_id}={a.status} vs {b.source_id}={b.status}",
                    a.index, b.index, _preferred(a, b)))
            # Project status.
            if a.project_status and b.project_status and a.project_status.lower() != b.project_status.lower():
                findings.append(ConflictFinding(
                    ConflictType.PROJECT_STATUS, ConflictSeverity.HIGH,
                    f"Project status conflict: {a.project_status} vs {b.project_status}",
                    a.index, b.index, _preferred(a, b)))
            # Company identity.
            if (a.normalized_company_name and b.normalized_company_name
                    and a.normalized_company_name != b.normalized_company_name):
                findings.append(ConflictFinding(
                    ConflictType.COMPANY_IDENTITY, ConflictSeverity.MEDIUM,
                    f"Company identity differs: {a.normalized_company_name} vs {b.normalized_company_name}",
                    a.index, b.index, _preferred(a, b)))
            # Location.
            if a.city and b.city and a.city.lower() != b.city.lower():
                findings.append(ConflictFinding(
                    ConflictType.LOCATION, ConflictSeverity.LOW,
                    f"Location differs: {a.city} vs {b.city}", a.index, b.index, _preferred(a, b)))
    return findings
