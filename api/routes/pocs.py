"""POC (decision-maker) discovery & enrichment endpoints (ContactOut, Prompt 44).

Company-level POC discovery for a lead's opportunity: real people are returned only
when ContactOut returns and validates them; otherwise role-only recommendations are
shown (never a fabricated person). Mutating/credit-spending endpoints are role-guarded
and rate-limited. The ContactOut API token is NEVER exposed in any response.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from api.dependencies import get_session
from api.security import rate_limit, require_role
from api.schemas import (
    ContactOutStatusResponse,
    POCDiscoveryResponse,
    POCListResponse,
    POCResponse,
    SourceCheckResponse,
    StakeholderRoleResponse,
)
from config import get_settings
from config.exceptions import NotFoundError
from database.models import DecisionMaker, Lead, UserRole, utcnow
from enrichment.contactout_poc import (
    discover_pocs_for_lead,
    enrich_poc,
    get_pocs_for_lead,
    resolve_company_for_lead,
)
from enrichment.stakeholder import recommend_for_lead
from integrations.contactout import ContactOutClient

logger = logging.getLogger("integrations.contactout")
router = APIRouter(tags=["pocs"])

# Credit-spending / outbound endpoints require SALES and are rate-limited.
_poc_role = require_role(UserRole.SALES)
_discover_limit = rate_limit("contactout_discover", 30)
_enrich_limit = rate_limit("contactout_enrich", 60)
_test_limit = rate_limit("contactout_test", 20)


def _roles_for(lead: Lead) -> tuple[list[StakeholderRoleResponse], int]:
    rec = recommend_for_lead(lead)
    roles = [StakeholderRoleResponse(role=r.role, role_category=r.role_category,
                                     decision_maker_type=r.decision_maker_type,
                                     relevance_score=r.relevance_score, reason=r.reason,
                                     is_primary=r.is_primary)
             for r in rec.recommended_roles]
    return roles, rec.recommendation_confidence


def _get_lead(session: Session, lead_id: int) -> Lead:
    lead = session.get(Lead, lead_id)
    if lead is None:
        raise NotFoundError(f"Lead {lead_id} not found.")
    return lead


@router.get("/leads/{lead_id}/pocs", response_model=POCListResponse,
            summary="POCs for a lead (real people + role-only recommendations)")
def list_lead_pocs(lead_id: int, session: Session = Depends(get_session)) -> POCListResponse:
    lead = _get_lead(session, lead_id)
    settings = get_settings()
    _company, company_name, _domain = resolve_company_for_lead(session, lead)
    pocs = get_pocs_for_lead(session, lead)
    roles, conf = _roles_for(lead)
    note = None
    if settings.contactout_config_status != "CONFIGURED":
        note = "POC enrichment is not configured."
    elif not pocs:
        note = "No verified POC found for this opportunity yet. Run discovery to search ContactOut."
    return POCListResponse(
        lead_id=lead.id, company_name=company_name,
        contactout_status=settings.contactout_config_status,
        pocs=[POCResponse.model_validate(p) for p in pocs],
        recommended_roles=roles, recommendation_confidence=conf, note=note,
    )


@router.post("/leads/{lead_id}/pocs/discover", response_model=POCDiscoveryResponse,
             summary="Discover real POCs for a lead's company via ContactOut")
def discover_lead_pocs(lead_id: int, force: bool = False,
                       session: Session = Depends(get_session),
                       role=Depends(_poc_role), _rl=Depends(_discover_limit)) -> POCDiscoveryResponse:
    lead = _get_lead(session, lead_id)
    summary = discover_pocs_for_lead(session, lead, force=force,
                                     actor=getattr(role, "value", str(role)))
    return POCDiscoveryResponse(
        lead_id=summary.lead_id, company_id=summary.company_id, company_name=summary.company_name,
        status=summary.status, candidates_found=summary.candidates_found,
        searches_used=summary.searches_used, enrichments_used=summary.enrichments_used,
        persisted=summary.persisted, reason=summary.reason, error_code=summary.error_code,
        pocs=[POCResponse.model_validate(p) for p in summary.pocs],
    )


@router.get("/pocs/{poc_id}", response_model=POCResponse, summary="Get a POC")
def get_poc(poc_id: int, session: Session = Depends(get_session)) -> POCResponse:
    dm = session.get(DecisionMaker, poc_id)
    if dm is None:
        raise NotFoundError(f"POC {poc_id} not found.")
    return POCResponse.model_validate(dm)


@router.post("/pocs/{poc_id}/enrich", response_model=POCDiscoveryResponse,
             summary="Re-enrich a stored POC via ContactOut")
def enrich_single_poc(poc_id: int, session: Session = Depends(get_session),
                      role=Depends(_poc_role), _rl=Depends(_enrich_limit)) -> POCDiscoveryResponse:
    dm = session.get(DecisionMaker, poc_id)
    if dm is None:
        raise NotFoundError(f"POC {poc_id} not found.")
    summary = enrich_poc(session, dm, actor=getattr(role, "value", str(role)))
    return POCDiscoveryResponse(
        lead_id=summary.lead_id, company_id=summary.company_id, company_name=summary.company_name,
        status=summary.status, candidates_found=summary.candidates_found,
        searches_used=summary.searches_used, enrichments_used=summary.enrichments_used,
        persisted=summary.persisted, reason=summary.reason, error_code=summary.error_code,
        pocs=[POCResponse.model_validate(p) for p in summary.pocs],
    )


@router.get("/integrations/contactout/status", response_model=ContactOutStatusResponse,
            summary="ContactOut integration config status (no token exposed)")
def contactout_status(session: Session = Depends(get_session)) -> ContactOutStatusResponse:
    s = get_settings()
    status = s.contactout_config_status
    note = {
        "CONFIGURED": "ContactOut is configured. Run a connection test to verify connectivity.",
        "NOT_CONFIGURED": "POC enrichment is not configured.",
        "DISABLED": "ContactOut integration is disabled.",
    }.get(status, status)
    return ContactOutStatusResponse(
        status=status, configured=bool(s.contactout_api_token), note=note,
        people_search_rate_per_minute=s.contactout_people_search_rate_per_minute,
        other_rate_per_minute=s.contactout_other_rate_per_minute,
        max_poc_searches_per_opportunity=s.contactout_max_poc_searches_per_opportunity,
        max_enrichments_per_opportunity=s.contactout_max_enrichments_per_opportunity,
        cache_ttl_hours=s.contactout_cache_ttl_hours,
    )


@router.post("/integrations/contactout/test", response_model=SourceCheckResponse,
             summary="Test ContactOut connectivity (no enrichment credits)")
def contactout_test(role=Depends(_poc_role), _rl=Depends(_test_limit)) -> SourceCheckResponse:
    """Real, credit-free connectivity check. Returns CONNECTED only after a real
    authenticated response; NOT_CONFIGURED without a token. Never claims LIVE VERIFIED
    without actually contacting ContactOut."""
    status, message = ContactOutClient().check_connection()
    return SourceCheckResponse(
        source_id="contactout", connection_status=status.value, message=message,
        performed_request=(status.value != "NOT_CONFIGURED"), checked_at=utcnow(),
    )
