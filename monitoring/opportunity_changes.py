"""Opportunity-level change detection (§11).

Recalculation alone is NOT a change — an event is emitted only when the
resulting opportunity state materially differs from before. Pure diff over two
real ``OpportunityCandidate`` states captured around a recompute.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from database.models import (
    AlertSeverity,
    AlertType,
    ChangeSignificance,
    OpportunityChangeEvent,
)

# Confidence must move by at least this to count as material (§11).
MATERIAL_CONFIDENCE_DELTA = 10


@dataclass(frozen=True)
class OpportunityState:
    opportunity_id: int | None = None
    company_id: int | None = None
    lead_id: int | None = None
    company_name: str | None = None
    confidence: int = 0
    evidence_confidence: int = 0
    status: str | None = None
    opportunity_types: tuple[str, ...] = ()


def _event(state, change_type, summary, old, new, significance) -> OpportunityChangeEvent:
    return OpportunityChangeEvent(
        opportunity_id=state.opportunity_id,
        company_id=state.company_id,
        lead_id=state.lead_id,
        change_type=change_type,
        summary=summary,
        old_value=(str(old) if old is not None else None),
        new_value=(str(new) if new is not None else None),
        significance=significance,
        dedup_key=f"opp:{state.opportunity_id or state.company_id}:{change_type}:{old}->{new}",
    )


def diff_opportunity(
    before: OpportunityState | None,
    after: OpportunityState,
    *,
    now: datetime,
    material_delta: int = MATERIAL_CONFIDENCE_DELTA,
) -> tuple[list[OpportunityChangeEvent], list["object"]]:
    """Pure opportunity-change diff (§11). Returns (events, findings)."""
    events: list[OpportunityChangeEvent] = []
    findings: list[object] = []

    if before is None:
        events.append(_event(after, "OPPORTUNITY_CREATED",
                             f"Opportunity created (confidence {after.confidence})",
                             None, after.confidence, ChangeSignificance.MEDIUM))
        return events, findings

    # Confidence movement (strength).
    delta = after.confidence - before.confidence
    if abs(delta) >= material_delta:
        ct = "OPPORTUNITY_STRENGTHENED" if delta > 0 else "OPPORTUNITY_WEAKENED"
        sig = ChangeSignificance.MEDIUM if delta > 0 else ChangeSignificance.LOW
        events.append(_event(after, ct, f"Confidence {before.confidence} → {after.confidence}",
                             before.confidence, after.confidence, sig))

    # Type change.
    if set(before.opportunity_types) != set(after.opportunity_types):
        events.append(_event(after, "OPPORTUNITY_TYPE_CHANGED",
                             f"Types {list(before.opportunity_types)} → {list(after.opportunity_types)}",
                             ",".join(before.opportunity_types) or None,
                             ",".join(after.opportunity_types) or None, ChangeSignificance.MEDIUM))

    # Evidence changed materially.
    ev_delta = after.evidence_confidence - before.evidence_confidence
    if abs(ev_delta) >= material_delta:
        events.append(_event(after, "OPPORTUNITY_EVIDENCE_CHANGED",
                             f"Evidence {before.evidence_confidence} → {after.evidence_confidence}",
                             before.evidence_confidence, after.evidence_confidence, ChangeSignificance.LOW))

    # Resolved / closed.
    if after.status != before.status and after.status in {"PROMOTED", "REJECTED"}:
        events.append(_event(after, "OPPORTUNITY_RESOLVED",
                             f"Status {before.status} → {after.status}",
                             before.status, after.status, ChangeSignificance.MEDIUM))

    return events, findings
