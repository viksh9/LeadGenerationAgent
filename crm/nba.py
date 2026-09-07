"""Next Best Action (§29). A deterministic recommendation based ONLY on the lead's
actual state (status, evidence, drafts, contacts, replies). It recommends — the
human decides — and never fabricates a reason."""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from database.models import (
    ActivityType,
    CRMActivity,
    DecisionMaker,
    EvidenceRecord,
    Lead,
    LeadStatus,
    OutreachDraft,
    OutreachDraftStatus,
)
from outreach.contacts import has_verified_business_email


def next_best_action(session: Session, lead: Lead) -> str:
    status = lead.status.value if hasattr(lead.status, "value") else str(lead.status)

    evidence_count = int(session.execute(
        select(func.count(EvidenceRecord.id)).where(EvidenceRecord.lead_id == lead.id)
    ).scalar() or 0)

    if status == LeadStatus.REPLIED.value:
        return "Review the reply and prepare a discovery call"
    if status == LeadStatus.MEETING.value:
        return "Prepare a proposal"
    if status == LeadStatus.QUALIFIED.value:
        return "Prepare and send a proposal"
    if status == LeadStatus.PROPOSAL.value:
        return "Follow up on the proposal"
    if status == LeadStatus.CONTACTED.value:
        return "Wait for a reply, then follow up if none arrives"
    if status in (LeadStatus.WON.value, LeadStatus.LOST.value, LeadStatus.DISQUALIFIED.value,
                  LeadStatus.NURTURE.value):
        return "No immediate action"

    # Pre-contact states.
    if evidence_count == 0:
        return "Verify supporting evidence before outreach"

    # Is there a draft in flight?
    draft = session.execute(
        select(OutreachDraft).where(OutreachDraft.lead_id == lead.id)
        .order_by(OutreachDraft.updated_at.desc()).limit(1)
    ).scalars().first()
    if draft is not None:
        if draft.status == OutreachDraftStatus.APPROVED:
            return "Send the approved email"
        if draft.status in (OutreachDraftStatus.DRAFT, OutreachDraftStatus.READY_FOR_REVIEW):
            return "Review the outreach draft and approve it"

    # Verified contact available?
    has_contact = False
    if lead.company_id:
        contacts = session.execute(
            select(DecisionMaker).where(DecisionMaker.company_id == lead.company_id).limit(50)
        ).scalars().all()
        has_contact = any(has_verified_business_email(c) for c in contacts)
    if not has_contact:
        return "Verify a business contact for the target role"

    if status == LeadStatus.OUTREACH_READY.value:
        return "Generate and review an outreach draft"
    return "Research the decision-maker and prepare outreach"
