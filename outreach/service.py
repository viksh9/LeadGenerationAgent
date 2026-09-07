"""Outreach draft lifecycle (§5, §6, §7, §30).

Generates human-reviewable DRAFTS grounded in REAL evidence, using the existing
deterministic ``pitch_generator`` (which only references real supplied numbers and
never asserts new facts). Every factual claim maps to the lead's real evidence
records via ``evidence_ids``. The system NEVER sends here — a draft must be
APPROVED by a human, and sending happens only through ``outreach.send`` with a
configured provider.

AI enhancement (§7) is optional and off by default: when enabled it may only
improve wording/clarity/CTA and its output is still bound to the same evidence —
it cannot introduce new factual claims.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy.orm import Session

from config.exceptions import NotFoundError, ValidationError
from crm.audit import record_audit
from database.models import (
    DecisionMaker,
    Lead,
    OutreachChannel,
    OutreachDraft,
    OutreachDraftStatus,
    utcnow,
)
from outreach.contacts import find_verified_contact_for_company, has_verified_business_email
from outreach.pitch_generator import run_pitch_generation


class OutreachService:
    def __init__(self, session: Session):
        self.session = session

    # ------------------------------------------------------------------ #
    def generate_draft(
        self,
        lead_id: int,
        *,
        channel: OutreachChannel = OutreachChannel.EMAIL,
        contact_id: int | None = None,
        actor: str = "human",
        now: datetime | None = None,
    ) -> OutreachDraft:
        now = now or utcnow()
        lead = self.session.get(Lead, lead_id)
        if lead is None:
            raise NotFoundError(f"Lead {lead_id} not found.")

        # Real evidence backing this lead (drives grounding + evidence_ids).
        from verification.service import EvidenceVerificationService
        evidence = EvidenceVerificationService(self.session).get_lead_evidence(lead_id)
        evidence_ids = [e.id for e in evidence]

        # Deterministic, evidence-safe message (reuses existing pitch generator).
        pitch = run_pitch_generation(lead)

        # Resolve a verified contact (never fabricated).
        contact = self._resolve_contact(lead, contact_id)
        recipient_email = contact.business_email if (contact and has_verified_business_email(contact)) else None

        # Grounding: a business claim must be backed by real evidence. With no
        # evidence, the draft stays DRAFT (not review-ready) and is flagged.
        grounding_ok = bool(evidence_ids)
        status = OutreachDraftStatus.READY_FOR_REVIEW if grounding_ok else OutreachDraftStatus.DRAFT

        draft = OutreachDraft(
            lead_id=lead_id, company_id=lead.company_id,
            contact_id=(contact.id if contact else None),
            target_role=(pitch.target_role or lead.primary_target_role),
            channel=channel,
            subject=pitch.email_subject,
            message=pitch.recommended_pitch,
            evidence_ids=evidence_ids,
            ai_generated=False,
            grounding_ok=grounding_ok,
            confidence=pitch.confidence,
            status=status,
            recipient_email=recipient_email,
            created_by=actor,
            created_at=now, updated_at=now,
        )
        self.session.add(draft)
        self.session.flush()
        record_audit(self.session, entity_type="outreach_draft", entity_id=draft.id,
                     action="GENERATE", actor=actor, new_value=status.value,
                     reason=("no supporting evidence" if not grounding_ok else None), now=now)
        return draft

    def _resolve_contact(self, lead: Lead, contact_id: int | None) -> DecisionMaker | None:
        if contact_id is not None:
            return self.session.get(DecisionMaker, contact_id)
        return find_verified_contact_for_company(
            self.session, lead.company_id, lead.normalized_company_name
        )

    # ------------------------------------------------------------------ #
    def get(self, draft_id: int) -> OutreachDraft | None:
        return self.session.get(OutreachDraft, draft_id)

    def approve(self, draft_id: int, *, approved_by: str = "human",
                now: datetime | None = None) -> OutreachDraft:
        """Human approval (§30). Only a reviewable draft can be approved."""
        now = now or utcnow()
        draft = self._require(draft_id)
        if draft.status not in (OutreachDraftStatus.DRAFT, OutreachDraftStatus.READY_FOR_REVIEW):
            raise ValidationError(f"Cannot approve a draft in status {draft.status.value}.")
        if not draft.grounding_ok:
            raise ValidationError(
                "Cannot approve an ungrounded draft (no supporting evidence). Add evidence first."
            )
        # Assign the idempotency key at approval so a subsequent send is protected.
        draft.status = OutreachDraftStatus.APPROVED
        draft.approved_by = approved_by
        draft.approved_at = now
        draft.idempotency_key = draft.idempotency_key or f"draft-{draft.id}-{uuid.uuid4().hex}"
        draft.updated_at = now
        self.session.flush()
        record_audit(self.session, entity_type="outreach_draft", entity_id=draft.id,
                     action="APPROVE", actor=approved_by, new_value="APPROVED", now=now)
        return draft

    def cancel(self, draft_id: int, *, actor: str = "human",
               now: datetime | None = None) -> OutreachDraft:
        now = now or utcnow()
        draft = self._require(draft_id)
        if draft.status == OutreachDraftStatus.SENT:
            raise ValidationError("Cannot cancel a draft that was already sent.")
        draft.status = OutreachDraftStatus.CANCELLED
        draft.updated_at = now
        self.session.flush()
        record_audit(self.session, entity_type="outreach_draft", entity_id=draft.id,
                     action="CANCEL", actor=actor, new_value="CANCELLED", now=now)
        return draft

    def update_content(self, draft_id: int, *, subject: str | None = None, message: str | None = None,
                       actor: str = "human", now: datetime | None = None) -> OutreachDraft:
        """Human edit of a not-yet-sent draft. Editing an approved draft returns it
        to review so it must be re-approved before sending."""
        now = now or utcnow()
        draft = self._require(draft_id)
        if draft.status in (OutreachDraftStatus.SENT, OutreachDraftStatus.CANCELLED):
            raise ValidationError(f"Cannot edit a draft in status {draft.status.value}.")
        if subject is not None:
            draft.subject = subject[:512]
        if message is not None:
            draft.message = message
        if draft.status == OutreachDraftStatus.APPROVED:
            draft.status = OutreachDraftStatus.READY_FOR_REVIEW
            draft.approved_by = None
            draft.approved_at = None
        draft.updated_at = now
        self.session.flush()
        record_audit(self.session, entity_type="outreach_draft", entity_id=draft.id,
                     action="EDIT", actor=actor, now=now)
        return draft

    def _require(self, draft_id: int) -> OutreachDraft:
        draft = self.get(draft_id)
        if draft is None:
            raise NotFoundError(f"Outreach draft {draft_id} not found.")
        return draft
