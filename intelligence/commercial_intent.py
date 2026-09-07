"""Deterministic commercial-intent classification (no LLM).

Commercial intent answers "how likely is there a real, current commercial
opportunity here?" — a SEPARATE axis from evidence confidence, source reliability,
and lead score. It is derived only from real, evidence-backed inputs (recency,
source quality, project/vendor/tender evidence, hiring volume, technology relevance,
signal combination). It never fabricates intent; with no qualifying evidence it
returns UNKNOWN.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from database.models import CommercialIntent


@dataclass
class IntentInputs:
    evidence_confidence: int = 0          # 0..100 (from evidence verification)
    is_fresh: bool = False                # signal/tender currently fresh (not stale)
    has_project_or_tender: bool = False   # a verified project/contract/tender signal
    has_vendor_or_award: bool = False     # vendor selected / award / RFP evidence
    active_it_jobs: int = 0               # current canonical IT openings
    distinct_signal_types: int = 0        # variety of corroborating signal types
    technology_relevant: bool = False     # IT-relevant technologies present
    company_resolved: bool = False        # canonical company identity established


@dataclass
class IntentResult:
    intent: CommercialIntent
    score: int                            # 0..100 internal composite (transparency only)
    reasons: list[str] = field(default_factory=list)


# Thresholds (configurable, not hard-coded per call site).
_VERY_HIGH, _HIGH, _MEDIUM, _LOW = 75, 55, 35, 15


def classify_commercial_intent(inp: IntentInputs) -> IntentResult:
    """Map real evidence-backed inputs to a commercial-intent band."""
    reasons: list[str] = []
    score = 0

    if inp.has_vendor_or_award:
        score += 30
        reasons.append("Vendor/award or RFP evidence present.")
    if inp.has_project_or_tender:
        score += 20
        reasons.append("Verified project/tender signal present.")
    if inp.active_it_jobs >= 10:
        score += 20
        reasons.append(f"{inp.active_it_jobs} active IT openings.")
    elif inp.active_it_jobs >= 3:
        score += 10
        reasons.append(f"{inp.active_it_jobs} active IT openings.")
    if inp.distinct_signal_types >= 2:
        score += 12
        reasons.append(f"{inp.distinct_signal_types} corroborating signal types.")
    if inp.technology_relevant:
        score += 8
        reasons.append("IT-relevant technologies identified.")
    # Recency and evidence quality gate/scale the score.
    if inp.is_fresh:
        score += 10
        reasons.append("Signal is current/fresh.")
    else:
        score = int(score * 0.6)
        reasons.append("Signal is not fresh — intent dampened.")
    score = min(100, int(score * (0.5 + inp.evidence_confidence / 200.0)))  # evidence scales 0.5..1.0
    if not inp.company_resolved:
        score = int(score * 0.7)
        reasons.append("Company identity unresolved — intent dampened.")

    # No qualifying commercial evidence at all → UNKNOWN, not LOW.
    if not (inp.has_project_or_tender or inp.has_vendor_or_award or inp.active_it_jobs > 0):
        return IntentResult(CommercialIntent.UNKNOWN, 0,
                            ["No project/tender/hiring evidence — intent unknown."])

    if score >= _VERY_HIGH:
        intent = CommercialIntent.VERY_HIGH
    elif score >= _HIGH:
        intent = CommercialIntent.HIGH
    elif score >= _MEDIUM:
        intent = CommercialIntent.MEDIUM
    elif score >= _LOW:
        intent = CommercialIntent.LOW
    else:
        intent = CommercialIntent.LOW
    return IntentResult(intent, score, reasons)
