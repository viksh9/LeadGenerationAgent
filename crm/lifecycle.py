"""Lead lifecycle state machine (§2, §3).

Transitions are EXPLICIT and validated. Crucially, a lead is NEVER automatically
moved to CONTACTED / REPLIED / MEETING unless a real event backs it:
* CONTACTED requires a provider-confirmed send (source ``SEND_CONFIRMED``),
* REPLIED requires a real inbound reply (source ``PROVIDER_REPLY``),
* MEETING requires a recorded meeting (source ``MEETING_RECORDED``),
* or an explicit human action (``changed_by="human"`` with a reason).

Every transition writes an immutable ``LeadStatusHistory`` row (§3), a
``STATUS_CHANGE`` CRM activity (§4/§36), and an ``AuditLog`` entry (§31).
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy.orm import Session

from config.exceptions import NotFoundError, ValidationError
from crm.activities import CRMActivityService
from crm.audit import record_audit
from database.models import (
    ActivityStatus,
    ActivityType,
    Lead,
    LeadStatus,
    LeadStatusHistory,
    utcnow,
)

# Allowed forward/side transitions. Same->same is a no-op (handled separately).
_ALLOWED: dict[LeadStatus, set[LeadStatus]] = {
    LeadStatus.NEW: {LeadStatus.RESEARCHED, LeadStatus.OUTREACH_READY, LeadStatus.NURTURE,
                     LeadStatus.DISQUALIFIED},
    LeadStatus.RESEARCHED: {LeadStatus.OUTREACH_READY, LeadStatus.NURTURE, LeadStatus.DISQUALIFIED},
    LeadStatus.OUTREACH_READY: {LeadStatus.CONTACTED, LeadStatus.RESEARCHED, LeadStatus.NURTURE,
                                LeadStatus.DISQUALIFIED},
    LeadStatus.CONTACTED: {LeadStatus.REPLIED, LeadStatus.MEETING, LeadStatus.NURTURE,
                           LeadStatus.LOST, LeadStatus.DISQUALIFIED},
    LeadStatus.REPLIED: {LeadStatus.MEETING, LeadStatus.QUALIFIED, LeadStatus.NURTURE,
                         LeadStatus.LOST, LeadStatus.DISQUALIFIED},
    LeadStatus.MEETING: {LeadStatus.QUALIFIED, LeadStatus.PROPOSAL, LeadStatus.NURTURE,
                         LeadStatus.LOST},
    LeadStatus.QUALIFIED: {LeadStatus.PROPOSAL, LeadStatus.NURTURE, LeadStatus.LOST},
    LeadStatus.PROPOSAL: {LeadStatus.WON, LeadStatus.LOST, LeadStatus.NURTURE},
    LeadStatus.WON: {LeadStatus.NURTURE},
    LeadStatus.LOST: {LeadStatus.NURTURE},
    LeadStatus.NURTURE: {LeadStatus.RESEARCHED, LeadStatus.OUTREACH_READY, LeadStatus.DISQUALIFIED},
    LeadStatus.DISQUALIFIED: {LeadStatus.NURTURE},
}

# Statuses that assert a real interaction happened — cannot be reached automatically
# without a real event source; a human may still set them explicitly (audited).
_EVENT_GATED: dict[LeadStatus, str] = {
    LeadStatus.CONTACTED: "SEND_CONFIRMED",
    LeadStatus.REPLIED: "PROVIDER_REPLY",
    LeadStatus.MEETING: "MEETING_RECORDED",
}


def _as_status(value) -> LeadStatus:
    if isinstance(value, LeadStatus):
        return value
    return LeadStatus(value)


class LeadLifecycleService:
    def __init__(self, session: Session):
        self.session = session
        self.activities = CRMActivityService(session)

    def can_transition(self, old: LeadStatus, new: LeadStatus) -> bool:
        if old == new:
            return True
        return new in _ALLOWED.get(old, set())

    def transition(
        self,
        lead_id: int,
        new_status: LeadStatus | str,
        *,
        changed_by: str = "SYSTEM",
        reason: str | None = None,
        source: str | None = None,
        now: datetime | None = None,
    ) -> Lead:
        """Move a lead to ``new_status`` with full validation + audit trail."""
        now = now or utcnow()
        new_status = _as_status(new_status)
        lead = self.session.get(Lead, lead_id)
        if lead is None:
            raise NotFoundError(f"Lead {lead_id} not found.")
        old_status = _as_status(lead.status)

        if old_status == new_status:
            return lead  # no-op; do not write history for a non-change

        if not self.can_transition(old_status, new_status):
            raise ValidationError(
                f"Illegal lead transition {old_status.value} -> {new_status.value}."
            )

        # Event-gate CONTACTED/REPLIED/MEETING (§2): only a real event source or an
        # explicit human action may assert the interaction happened.
        required_source = _EVENT_GATED.get(new_status)
        is_human = (changed_by or "").lower() == "human"
        if required_source and not is_human and source != required_source:
            raise ValidationError(
                f"Cannot auto-advance lead to {new_status.value} without a real event "
                f"(source '{required_source}') or explicit human action."
            )

        lead.status = new_status
        lead.updated_at = now
        self.session.flush()

        self.session.add(LeadStatusHistory(
            lead_id=lead_id, old_status=old_status.value, new_status=new_status.value,
            changed_by=changed_by, reason=reason, source=source, created_at=now,
        ))
        self.activities.log(
            activity_type=ActivityType.STATUS_CHANGE, lead_id=lead_id, company_id=lead.company_id,
            status=ActivityStatus.COMPLETED, subject=f"Status {old_status.value} → {new_status.value}",
            body_reference=reason, source=source or "INTERNAL",
            is_system_event=not is_human, created_by=changed_by, now=now,
        )
        record_audit(
            self.session, entity_type="lead", entity_id=lead_id, action="STATUS_CHANGE",
            actor=changed_by, old_value=old_status.value, new_value=new_status.value,
            source=source, reason=reason, now=now,
        )
        self.session.flush()
        return lead

    def history(self, lead_id: int) -> list[LeadStatusHistory]:
        from sqlalchemy import select
        return list(self.session.execute(
            select(LeadStatusHistory).where(LeadStatusHistory.lead_id == lead_id)
            .order_by(LeadStatusHistory.created_at.asc(), LeadStatusHistory.id.asc())
        ).scalars().all())
