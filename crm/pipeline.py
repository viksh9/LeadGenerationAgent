"""Sales pipeline service (§22, §23).

Manages ``SalesOpportunity`` records and their pipeline stage. Key real-data rules:
* ``estimated_value`` is NEVER inferred — it exists only when a user enters it
  (``value_source="USER"``) or it is evidence-supported (``value_source="EVIDENCE"``);
  otherwise ``value_source="NOT_AVAILABLE"`` and the value stays null (§22, §26).
* ``probability`` is a sales judgement, distinct from ``lead_score`` (§23) — it is
  never auto-derived from the lead score.
* Stage changes are validated and audited; WON/LOST are terminal-ish sales
  outcomes that callers should gate behind human approval (§30).
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from config.exceptions import NotFoundError, ValidationError
from crm.activities import CRMActivityService
from crm.audit import record_audit
from database.models import (
    ActivityType,
    DataProvenance,
    Lead,
    OpportunityCandidate,
    SalesOpportunity,
    SalesStage,
    utcnow,
)

_STAGE_ORDER = [
    SalesStage.IDENTIFIED, SalesStage.RESEARCHED, SalesStage.OUTREACH_READY, SalesStage.CONTACTED,
    SalesStage.ENGAGED, SalesStage.QUALIFIED, SalesStage.DISCOVERY, SalesStage.PROPOSAL,
    SalesStage.NEGOTIATION, SalesStage.WON,
]
_TERMINAL = {SalesStage.WON, SalesStage.LOST}


def _as_stage(value) -> SalesStage:
    return value if isinstance(value, SalesStage) else SalesStage(value)


class SalesPipelineService:
    def __init__(self, session: Session):
        self.session = session
        self.activities = CRMActivityService(session)

    def get(self, opp_id: int) -> SalesOpportunity | None:
        return self.session.get(SalesOpportunity, opp_id)

    def list(self, *, stage: SalesStage | None = None, company_id: int | None = None,
             limit: int = 100, offset: int = 0) -> list[SalesOpportunity]:
        stmt = select(SalesOpportunity)
        if stage is not None:
            stmt = stmt.where(SalesOpportunity.stage == stage)
        if company_id is not None:
            stmt = stmt.where(SalesOpportunity.company_id == company_id)
        stmt = stmt.order_by(SalesOpportunity.updated_at.desc()).limit(limit).offset(offset)
        return list(self.session.execute(stmt).scalars().all())

    def create(
        self, *, title: str, company_id: int | None = None, lead_id: int | None = None,
        opportunity_type: str | None = None, description: str | None = None,
        estimated_team_scale: str | None = None,
        estimated_value: float | None = None, estimated_value_currency: str | None = None,
        value_source: str = "NOT_AVAILABLE", confidence: int = 0,
        evidence_ids: list[int] | None = None, stage: SalesStage = SalesStage.IDENTIFIED,
        owner: str | None = None, source: str | None = "INTERNAL",
        actor: str = "human", now: datetime | None = None,
    ) -> SalesOpportunity:
        now = now or utcnow()
        # Guard: a monetary value must declare a legitimate source (§22/§26).
        if estimated_value is not None and value_source not in ("USER", "EVIDENCE"):
            raise ValidationError(
                "estimated_value requires value_source USER or EVIDENCE; deal value is never inferred."
            )
        if estimated_value is None:
            value_source = "NOT_AVAILABLE"
        opp = SalesOpportunity(
            title=title[:255], company_id=company_id, lead_id=lead_id,
            opportunity_type=opportunity_type, description=description,
            estimated_team_scale=estimated_team_scale, estimated_value=estimated_value,
            estimated_value_currency=estimated_value_currency, value_source=value_source,
            confidence=confidence, evidence_ids=list(evidence_ids or []), stage=_as_stage(stage),
            owner=owner, source=source, data_provenance=DataProvenance.REAL,
            created_at=now, updated_at=now,
        )
        self.session.add(opp)
        self.session.flush()
        record_audit(self.session, entity_type="sales_opportunity", entity_id=opp.id,
                     action="CREATE", actor=actor, new_value=title, source=source, now=now)
        self.activities.log(activity_type=ActivityType.NOTE, company_id=company_id, lead_id=lead_id,
                            opportunity_id=opp.id, subject=f"Opportunity created: {title}",
                            is_system_event=(actor != "human"), created_by=actor, now=now)
        return opp

    def promote_from_candidate(self, candidate_id: int, *, actor: str = "human",
                               now: datetime | None = None) -> SalesOpportunity:
        """Create a managed opportunity from a real analytical OpportunityCandidate.
        No monetary value is invented — value stays NOT_AVAILABLE until entered."""
        cand = self.session.get(OpportunityCandidate, candidate_id)
        if cand is None:
            raise NotFoundError(f"Opportunity candidate {candidate_id} not found.")
        return self._create_from_candidate(cand, candidate_id, actor, now)

    def _create_from_candidate(self, cand, candidate_id, actor, now):
        now = now or utcnow()
        title = f"{cand.company_name}: {', '.join(cand.opportunity_types or ['opportunity'])}"[:255]
        opp = SalesOpportunity(
            title=title, lead_id=cand.lead_id, opportunity_candidate_id=candidate_id,
            opportunity_type=(cand.opportunity_types or [None])[0], description=cand.reason,
            confidence=cand.confidence or 0, value_source="NOT_AVAILABLE",
            stage=SalesStage.IDENTIFIED, source="CANDIDATE", data_provenance=DataProvenance.REAL,
            created_at=now, updated_at=now,
        )
        self.session.add(opp)
        self.session.flush()
        record_audit(self.session, entity_type="sales_opportunity", entity_id=opp.id,
                     action="PROMOTE_FROM_CANDIDATE", actor=actor, new_value=title, now=now)
        return opp

    def set_stage(self, opp_id: int, stage: SalesStage | str, *, actor: str = "human",
                  reason: str | None = None, now: datetime | None = None) -> SalesOpportunity:
        now = now or utcnow()
        stage = _as_stage(stage)
        opp = self.get(opp_id)
        if opp is None:
            raise NotFoundError(f"Sales opportunity {opp_id} not found.")
        old = _as_stage(opp.stage)
        if old == stage:
            return opp
        opp.stage = stage
        opp.updated_at = now
        self.session.flush()
        record_audit(self.session, entity_type="sales_opportunity", entity_id=opp_id,
                     action="STAGE_CHANGE", actor=actor, old_value=old.value, new_value=stage.value,
                     reason=reason, now=now)
        self.activities.log(activity_type=ActivityType.NOTE, company_id=opp.company_id,
                            lead_id=opp.lead_id, opportunity_id=opp_id,
                            subject=f"Stage {old.value} → {stage.value}", body_reference=reason,
                            is_system_event=(actor != "human"), created_by=actor, now=now)
        return opp

    def set_value(self, opp_id: int, *, estimated_value: float | None, currency: str | None = None,
                  value_source: str = "USER", actor: str = "human",
                  now: datetime | None = None) -> SalesOpportunity:
        now = now or utcnow()
        opp = self.get(opp_id)
        if opp is None:
            raise NotFoundError(f"Sales opportunity {opp_id} not found.")
        if estimated_value is not None and value_source not in ("USER", "EVIDENCE"):
            raise ValidationError("estimated_value requires value_source USER or EVIDENCE.")
        old = opp.estimated_value
        opp.estimated_value = estimated_value
        opp.estimated_value_currency = currency
        opp.value_source = value_source if estimated_value is not None else "NOT_AVAILABLE"
        opp.updated_at = now
        self.session.flush()
        record_audit(self.session, entity_type="sales_opportunity", entity_id=opp_id,
                     action="SET_VALUE", actor=actor, old_value=old, new_value=estimated_value, now=now)
        return opp

    def set_probability(self, opp_id: int, probability: int | None, *, actor: str = "human",
                        now: datetime | None = None) -> SalesOpportunity:
        now = now or utcnow()
        if probability is not None and not (0 <= probability <= 100):
            raise ValidationError("probability must be between 0 and 100.")
        opp = self.get(opp_id)
        if opp is None:
            raise NotFoundError(f"Sales opportunity {opp_id} not found.")
        opp.probability = probability
        opp.updated_at = now
        self.session.flush()
        record_audit(self.session, entity_type="sales_opportunity", entity_id=opp_id,
                     action="SET_PROBABILITY", actor=actor, new_value=probability, now=now)
        return opp
