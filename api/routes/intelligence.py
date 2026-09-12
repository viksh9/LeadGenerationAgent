"""Lead Intelligence endpoints (Prompt 50, §43).

Aggregation read-model over existing engines. GET is open (deterministic, cached — no
provider call forced). The refresh POST re-runs the bounded AI analysis and is
role-guarded + rate-limited so provider calls never happen on every page load (§44/§45).
No new URL prefix — follows the codebase convention (routes declare full paths).
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from api.dependencies import get_session
from api.schemas import (
    CompanyProfileResponse,
    LeadIntelligenceResponse,
    LeadSourcesResponse,
    OpportunityViewResponse,
    POCIntelligenceResponse,
    POCResponse,
    ProfileHighlightsResponse,
    SourceRefResponse,
    StakeholderRoleResponse,
)
from api.security import rate_limit, require_role
from config.exceptions import NotFoundError
from database.models import Lead, UserRole
from intelligence.lead_intelligence import (
    LeadIntelligence,
    POCIntelligence,
    build_lead_intelligence,
    lead_sources,
)

router = APIRouter(tags=["intelligence"])

_refresh_role = require_role(UserRole.SALES)
_refresh_limit = rate_limit("intelligence_refresh", 20)


def _get_lead(session: Session, lead_id: int) -> Lead:
    lead = session.get(Lead, lead_id)
    if lead is None:
        raise NotFoundError(f"Lead {lead_id} not found.")
    return lead


def _poc_response(pi: POCIntelligence) -> POCIntelligenceResponse:
    return POCIntelligenceResponse(
        poc=POCResponse.model_validate(pi.poc), poc_status=pi.poc_status,
        role_match_score=pi.role_match_score, contact_trust_score=pi.contact_trust_score,
        contact_trust_status=pi.contact_trust_status, is_primary=pi.is_primary)


def _to_response(intel: LeadIntelligence) -> LeadIntelligenceResponse:
    roles = [StakeholderRoleResponse(role=r.role, role_category=r.role_category,
                                     decision_maker_type=r.decision_maker_type,
                                     relevance_score=r.relevance_score, reason=r.reason,
                                     is_primary=r.is_primary) for r in intel.recommended_roles]
    ov = intel.opportunity
    return LeadIntelligenceResponse(
        lead_id=intel.lead_id, company_id=intel.company_id, company_name=intel.company_name,
        lead_score=intel.lead_score, lead_priority=intel.lead_priority,
        data_trust=intel.data_trust, contact_trust=intel.contact_trust,
        signal_summary=intel.signal_summary,
        company_profile=CompanyProfileResponse(**intel.company_profile.as_dict()),
        opportunity=OpportunityViewResponse(
            opportunity_type=ov.opportunity_type, label=ov.label, staffing_need=ov.staffing_need,
            estimated_team=ov.estimated_team, urgency=ov.urgency, technologies=ov.technologies,
            signals=ov.signals),
        recommended_roles=roles, recommendation_confidence=intel.recommendation_confidence,
        primary_poc=_poc_response(intel.primary_poc) if intel.primary_poc else None,
        secondary_pocs=[_poc_response(p) for p in intel.secondary_pocs],
        ai_highlights=ProfileHighlightsResponse(**intel.ai_highlights.as_dict()),
        sources=[SourceRefResponse(**s.as_dict()) for s in intel.sources],
        freshness_score=intel.freshness_score, freshness_status=intel.freshness_status,
        sales_action=intel.sales_action, generated_at=intel.generated_at)


@router.get("/leads/{lead_id}/intelligence", response_model=LeadIntelligenceResponse,
            summary="Aggregated lead intelligence (company + signal + POC + trust + AI highlights)")
def get_lead_intelligence(lead_id: int, session: Session = Depends(get_session)) -> LeadIntelligenceResponse:
    lead = _get_lead(session, lead_id)
    return _to_response(build_lead_intelligence(session, lead, refresh=False))


@router.get("/leads/{lead_id}/sources", response_model=LeadSourcesResponse,
            summary="All contributing sources for a lead (field-level provenance)")
def get_lead_sources(lead_id: int, session: Session = Depends(get_session)) -> LeadSourcesResponse:
    lead = _get_lead(session, lead_id)
    from enrichment.contactout_poc import resolve_company_for_lead
    company, company_name, _ = resolve_company_for_lead(session, lead)
    return LeadSourcesResponse(
        lead_id=lead.id, company_id=(company.id if company else None), company_name=company_name,
        sources=[SourceRefResponse(**s.as_dict()) for s in lead_sources(session, lead)])


@router.post("/leads/{lead_id}/intelligence/refresh", response_model=LeadIntelligenceResponse,
             summary="Recompute lead intelligence (bounded AI re-analysis)")
def refresh_lead_intelligence(lead_id: int, session: Session = Depends(get_session),
                              role=Depends(_refresh_role), _rl=Depends(_refresh_limit)
                              ) -> LeadIntelligenceResponse:
    lead = _get_lead(session, lead_id)
    return _to_response(build_lead_intelligence(session, lead, refresh=True))
