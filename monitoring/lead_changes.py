"""Lead-level change detection (§10).

Detects material changes between a lead's state BEFORE and AFTER a real
recompute (score/priority, evidence strength, conflicts, contact verification,
outreach readiness). Because it compares two real states captured around the
recompute, it never guesses — a change is emitted only when the values actually
moved. Emits ``LeadChangeEvent`` rows and Findings for the alert service.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from database.models import (
    AlertSeverity,
    AlertType,
    ChangeSignificance,
    LeadChangeEvent,
    LeadPriority,
)
from monitoring.config import DEFAULT_LEAD_CHANGE, LeadChangeConfig
from monitoring.findings import Finding

# Priority rank for detecting upgrades vs downgrades.
_PRIORITY_RANK = {
    LeadPriority.LOW.value: 0,
    LeadPriority.NURTURE.value: 1,
    LeadPriority.WARM.value: 2,
    LeadPriority.HOT.value: 3,
}


@dataclass(frozen=True)
class LeadState:
    """Snapshot of a lead's scoring/evidence state for change comparison."""

    lead_id: int
    company_id: int | None = None
    company_name: str | None = None
    lead_score: float = 0.0
    lead_priority: str = LeadPriority.LOW.value
    evidence_confidence: int = 0
    verification_status: str | None = None
    lead_readiness: str | None = None
    conflict_count: int = 0
    verified_contact_count: int = 0


def _priority_rank(value: str | None) -> int:
    return _PRIORITY_RANK.get(value or LeadPriority.LOW.value, 0)


def _event(lead_id, company_id, change_type, summary, old, new, significance) -> LeadChangeEvent:
    return LeadChangeEvent(
        lead_id=lead_id,
        company_id=company_id,
        change_type=change_type,
        summary=summary,
        old_value=(str(old) if old is not None else None),
        new_value=(str(new) if new is not None else None),
        significance=significance,
        dedup_key=f"lead:{lead_id}:{change_type}:{old}->{new}",
    )


def diff_lead(
    before: LeadState | None,
    after: LeadState,
    *,
    now: datetime,
    config: LeadChangeConfig = DEFAULT_LEAD_CHANGE,
) -> tuple[list[LeadChangeEvent], list[Finding]]:
    """Pure lead-change diff (§10). ``before=None`` means a newly created lead."""
    events: list[LeadChangeEvent] = []
    findings: list[Finding] = []
    lid, cid = after.lead_id, after.company_id
    link = f"/leads/{lid}"

    # Newly created high-intent lead.
    if before is None:
        if after.lead_priority == LeadPriority.HOT.value:
            findings.append(Finding(
                alert_type=AlertType.NEW_HIGH_INTENT_LEAD, severity=AlertSeverity.HIGH,
                title=f"New HOT lead: {after.company_name or 'company'}",
                message=f"Lead scored {round(after.lead_score)} (HOT) on creation.",
                dedup_key=f"lead:{lid}:NEW_HOT", company_id=cid, lead_id=lid, link=link,
            ))
        return events, findings

    # Score movement.
    delta = after.lead_score - before.lead_score
    if abs(delta) >= config.min_score_delta:
        up = delta > 0
        sig = ChangeSignificance.HIGH if abs(delta) >= config.strong_score_delta else ChangeSignificance.MEDIUM
        ct = "SCORE_INCREASED" if up else "SCORE_DECREASED"
        events.append(_event(lid, cid, ct, f"Lead score {round(before.lead_score)} → {round(after.lead_score)}",
                             round(before.lead_score), round(after.lead_score), sig))
        if up:
            findings.append(Finding(
                alert_type=AlertType.LEAD_SCORE_INCREASED, severity=AlertSeverity.MEDIUM,
                title=f"Lead score up +{round(delta)}: {after.company_name or 'company'}",
                message=f"Score {round(before.lead_score)} → {round(after.lead_score)}.",
                dedup_key=f"lead:{lid}:SCORE_UP:{round(before.lead_score)}->{round(after.lead_score)}",
                company_id=cid, lead_id=lid, link=link,
            ))

    # Priority change.
    if after.lead_priority != before.lead_priority:
        upgraded = _priority_rank(after.lead_priority) > _priority_rank(before.lead_priority)
        sig = ChangeSignificance.HIGH if upgraded else ChangeSignificance.MEDIUM
        events.append(_event(lid, cid, "PRIORITY_CHANGED",
                             f"Priority {before.lead_priority} → {after.lead_priority}",
                             before.lead_priority, after.lead_priority, sig))
        if upgraded:
            became_hot = after.lead_priority == LeadPriority.HOT.value
            findings.append(Finding(
                alert_type=(AlertType.NEW_HIGH_INTENT_LEAD if became_hot else AlertType.LEAD_PRIORITY_INCREASED),
                severity=(AlertSeverity.HIGH if became_hot else AlertSeverity.MEDIUM),
                title=f"Priority up ({after.lead_priority}): {after.company_name or 'company'}",
                message=f"Lead priority rose {before.lead_priority} → {after.lead_priority}.",
                dedup_key=f"lead:{lid}:PRIORITY_UP:{before.lead_priority}->{after.lead_priority}",
                company_id=cid, lead_id=lid, link=link,
            ))

    # Evidence strengthened / weakened.
    ev_delta = after.evidence_confidence - before.evidence_confidence
    if abs(ev_delta) >= config.min_score_delta:
        ct = "EVIDENCE_STRENGTHENED" if ev_delta > 0 else "EVIDENCE_WEAKENED"
        events.append(_event(lid, cid, ct,
                             f"Evidence confidence {before.evidence_confidence} → {after.evidence_confidence}",
                             before.evidence_confidence, after.evidence_confidence, ChangeSignificance.MEDIUM))

    # New conflict detected.
    if after.conflict_count > before.conflict_count:
        events.append(_event(lid, cid, "CONFLICT_DETECTED",
                             f"Conflicts {before.conflict_count} → {after.conflict_count}",
                             before.conflict_count, after.conflict_count, ChangeSignificance.HIGH))
        findings.append(Finding(
            alert_type=AlertType.EVIDENCE_CONFLICT, severity=AlertSeverity.HIGH,
            title=f"Evidence conflict: {after.company_name or 'company'}",
            message=f"New conflicting evidence detected ({after.conflict_count} total).",
            dedup_key=f"lead:{lid}:CONFLICT:{after.conflict_count}",
            company_id=cid, lead_id=lid, link=link,
        ))

    # Contact became verified.
    if after.verified_contact_count > before.verified_contact_count:
        events.append(_event(lid, cid, "CONTACT_VERIFIED",
                             f"Verified contacts {before.verified_contact_count} → {after.verified_contact_count}",
                             before.verified_contact_count, after.verified_contact_count, ChangeSignificance.MEDIUM))
        findings.append(Finding(
            alert_type=AlertType.CONTACT_VERIFIED, severity=AlertSeverity.MEDIUM,
            title=f"Verified contact: {after.company_name or 'company'}",
            message="A decision-maker contact became verified for this lead.",
            dedup_key=f"lead:{lid}:CONTACT_VERIFIED:{after.verified_contact_count}",
            company_id=cid, lead_id=lid, link=link,
        ))

    # Became outreach-ready.
    if after.lead_readiness == "READY" and before.lead_readiness != "READY":
        events.append(_event(lid, cid, "OUTREACH_READY", "Lead became outreach-ready",
                             before.lead_readiness, after.lead_readiness, ChangeSignificance.MEDIUM))

    # Became stale.
    if after.verification_status == "STALE" and before.verification_status != "STALE":
        events.append(_event(lid, cid, "EVIDENCE_STALE", "Lead evidence became stale",
                             before.verification_status, after.verification_status, ChangeSignificance.MEDIUM))
        findings.append(Finding(
            alert_type=AlertType.EVIDENCE_STALE, severity=AlertSeverity.MEDIUM,
            title=f"Evidence stale: {after.company_name or 'company'}",
            message="Supporting evidence for this lead is now stale.",
            dedup_key=f"lead:{lid}:STALE",
            company_id=cid, lead_id=lid, link=link,
        ))

    return events, findings
