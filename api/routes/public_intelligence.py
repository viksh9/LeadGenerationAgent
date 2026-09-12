"""Free/public intelligence endpoints (Prompt 45).

Discovers legitimately PUBLIC company + POC intelligence from free sources. Real data
only — no fabricated people/emails/phones. Discovery/test endpoints are role-guarded
(SALES) and rate-limited; no provider credentials are ever exposed.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from api.dependencies import get_session
from api.schemas import (
    CompanyFieldSourceResponse,
    CompanyIntelDiscoveryResponse,
    CompanyLocationResponse,
    CompanyPublicIntelligenceResponse,
    POCResponse,
    PublicIntelligenceDiscoveryResponse,
    PublicIntelligenceTestResponse,
)
from api.security import rate_limit, require_role
from collectors.base import HealthStatus
from config import get_settings
from config.exceptions import NotFoundError, ValidationError
from database.models import Company, Lead, UserRole, utcnow
from enrichment.contactout_poc import get_pocs_for_lead
from enrichment.public_intelligence_service import (
    PUBLIC_SOURCE_TYPES,
    discover_company_intelligence,
    discover_public_intelligence_for_lead,
    get_public_pocs_for_lead,
)
from integrations.public_intelligence import build_providers

logger = logging.getLogger("integrations.public_intelligence")
router = APIRouter(tags=["public-intelligence"])

_pi_role = require_role(UserRole.SALES)
_discover_limit = rate_limit("public_intelligence_discover", 30)
_test_limit = rate_limit("public_intelligence_test", 20)

_HEALTH_TO_RESULT = {
    HealthStatus.HEALTHY: "LIVE_VERIFIED",
    HealthStatus.DEGRADED: "LIVE_VERIFIED",
    HealthStatus.RATE_LIMITED: "SOURCE_UNAVAILABLE",
    HealthStatus.UNAVAILABLE: "SOURCE_UNAVAILABLE",
    HealthStatus.NOT_CONFIGURED: "NOT_CONFIGURED",
}


def _get_lead(session: Session, lead_id: int) -> Lead:
    lead = session.get(Lead, lead_id)
    if lead is None:
        raise NotFoundError(f"Lead {lead_id} not found.")
    return lead


@router.post("/leads/{lead_id}/public-intelligence/discover",
             response_model=PublicIntelligenceDiscoveryResponse,
             summary="Discover public company + POC intelligence for a lead")
def discover_public_intelligence(lead_id: int, force: bool = False,
                                 session: Session = Depends(get_session),
                                 role=Depends(_pi_role), _rl=Depends(_discover_limit)
                                 ) -> PublicIntelligenceDiscoveryResponse:
    lead = _get_lead(session, lead_id)
    summary = discover_public_intelligence_for_lead(
        session, lead, force=force, actor=getattr(role, "value", str(role)))
    return PublicIntelligenceDiscoveryResponse(
        lead_id=summary.lead_id, company_id=summary.company_id, company_name=summary.company_name,
        status=summary.status, people_found=summary.people_found, persisted=summary.persisted,
        provider_status=summary.provider_status, company_facts_updated=summary.company_facts_updated,
        reason=summary.reason, pocs=[POCResponse.model_validate(p) for p in summary.pocs],
    )


@router.post("/companies/{company_id}/public-intelligence/discover",
             response_model=CompanyIntelDiscoveryResponse,
             summary="Discover official company intelligence (website/address/contacts)")
def discover_company_public_intelligence(company_id: int, force: bool = False,
                                         session: Session = Depends(get_session),
                                         role=Depends(_pi_role), _rl=Depends(_discover_limit)
                                         ) -> CompanyIntelDiscoveryResponse:
    company = session.get(Company, company_id)
    if company is None:
        raise NotFoundError(f"Company {company_id} not found.")
    summary = discover_company_intelligence(session, company, force=force,
                                            actor=getattr(role, "value", str(role)))
    return CompanyIntelDiscoveryResponse(
        company_id=summary.company_id, company_name=summary.company_name, status=summary.status,
        provider_status=summary.provider_status, fields_updated=summary.fields_updated,
        people_persisted=summary.people_persisted, data_trust_score=summary.data_trust_score,
        reason=summary.reason)


@router.get("/companies/{company_id}/public-intelligence",
            response_model=CompanyPublicIntelligenceResponse,
            summary="Company profile (with field sources) + real public leadership")
def company_public_intelligence(company_id: int, session: Session = Depends(get_session)
                                ) -> CompanyPublicIntelligenceResponse:
    company = session.get(Company, company_id)
    if company is None:
        raise NotFoundError(f"Company {company_id} not found.")
    from sqlalchemy import select
    from database.models import (CompanyFieldEvidence, CompanyLocation, DataProvenance,
                                 DecisionMaker)
    people = session.scalars(select(DecisionMaker).where(
        DecisionMaker.company_id == company.id,
        DecisionMaker.source_type.in_(PUBLIC_SOURCE_TYPES),
        DecisionMaker.full_name.isnot(None),
        DecisionMaker.data_provenance == DataProvenance.REAL,
    )).all()
    people = sorted(people, key=lambda d: (d.match_score or 0, d.contact_trust_score or 0), reverse=True)
    locations = session.scalars(select(CompanyLocation).where(
        CompanyLocation.company_id == company.id)).all()
    # Canonical field source = highest-priority evidence per field.
    ev_rows = session.scalars(select(CompanyFieldEvidence).where(
        CompanyFieldEvidence.company_id == company.id)).all()
    best_by_field: dict[str, CompanyFieldEvidence] = {}
    for e in sorted(ev_rows, key=lambda x: x.source_priority):
        best_by_field.setdefault(e.field, e)
    return CompanyPublicIntelligenceResponse(
        company_id=company.id, company_name=company.canonical_name,
        website=company.website, linkedin_url=company.linkedin_url, industry=company.industry,
        city=company.headquarters_city, state=company.headquarters_state,
        country=company.headquarters_country, full_address=company.full_address,
        postal_code=company.postal_code, company_phone=company.company_phone,
        company_email=company.company_email, contact_url=company.contact_url,
        careers_url=company.careers_url, leadership_url=company.leadership_url,
        wikidata_id=company.wikidata_id, data_trust_score=company.data_trust_score or 0,
        official_verified_at=company.official_verified_at,
        india_locations=list(company.india_locations or []),
        locations=[CompanyLocationResponse.model_validate(l) for l in locations],
        field_sources=[CompanyFieldSourceResponse.model_validate(e) for e in best_by_field.values()],
        public_leadership=[POCResponse.model_validate(p) for p in people],
    )


@router.get("/companies/{company_id}/sources",
            response_model=list[CompanyFieldSourceResponse],
            summary="All field-level company evidence (provenance, conflicts retained)")
def company_sources(company_id: int, session: Session = Depends(get_session)
                    ) -> list[CompanyFieldSourceResponse]:
    if session.get(Company, company_id) is None:
        raise NotFoundError(f"Company {company_id} not found.")
    from sqlalchemy import select
    from database.models import CompanyFieldEvidence
    rows = session.scalars(select(CompanyFieldEvidence).where(
        CompanyFieldEvidence.company_id == company_id).order_by(
        CompanyFieldEvidence.field, CompanyFieldEvidence.source_priority)).all()
    return [CompanyFieldSourceResponse.model_validate(e) for e in rows]


@router.post("/public-intelligence/test", response_model=PublicIntelligenceTestResponse,
             summary="Real connectivity test against a configured public source")
def public_intelligence_test(provider: str = Query("wikidata"),
                             role=Depends(_pi_role), _rl=Depends(_test_limit)
                             ) -> PublicIntelligenceTestResponse:
    """Makes a real, cheap HTTP request to a public source and reports the outcome.
    Never claims LIVE_VERIFIED without an actual request."""
    settings = get_settings()
    if not settings.public_intelligence_provider_enabled(provider):
        return PublicIntelligenceTestResponse(
            provider=provider, result="NOT_CONFIGURED", status="NOT_CONFIGURED",
            message=f"Provider '{provider}' is not enabled.", performed_request=False,
            checked_at=utcnow())
    built = build_providers(names=[provider])
    if not built:
        raise ValidationError(f"Unknown public-intelligence provider '{provider}'.")
    status, message = built[0].health_check()
    return PublicIntelligenceTestResponse(
        provider=provider, result=_HEALTH_TO_RESULT.get(status, "ERROR"), status=status.value,
        message=message, performed_request=(status != HealthStatus.NOT_CONFIGURED), checked_at=utcnow())
