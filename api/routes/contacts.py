"""Decision-maker / contact / stakeholder endpoints (real, source-backed only).

Exposes recommended stakeholder ROLES (no person) distinctly from VERIFIED people
and business contacts. Enrichment is an explicit, on-demand, official-source-only
operation. Provider credentials are never exposed.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from api.dependencies import get_session
from api.schemas import (
    DecisionMakerListResponse,
    DecisionMakerResponse,
    EnrichRunResponse,
    LeadStakeholdersResponse,
    StakeholderRoleResponse,
)
from collectors.raw_record import normalize_company_name
from company import repository as company_repo
from config.exceptions import NotFoundError, ValidationError
from config.settings import get_settings
from database.models import Company, DataProvenance, DecisionMaker, RoleCategory, VerificationStatus
from database.repository import get_lead
from enrichment.enrichment_service import enrich_company
from enrichment.outreach import OutreachInputs, classify_outreach_readiness
from enrichment.stakeholder import recommend_for_lead

logger = logging.getLogger(__name__)
router = APIRouter(tags=["contacts"])
MAX_PAGE_SIZE = 100
_VERIFIED = (VerificationStatus.VERIFIED, VerificationStatus.PARTIALLY_VERIFIED)


def _prov() -> DataProvenance | None:
    return None if get_settings().synthetic_leads_visible else DataProvenance.REAL


@router.get("/contacts", response_model=DecisionMakerListResponse, summary="List decision makers / contacts")
def list_contacts(
    session: Session = Depends(get_session),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=MAX_PAGE_SIZE),
    company: str | None = Query(None),
    role_category: RoleCategory | None = Query(None),
    verification_status: VerificationStatus | None = Query(None),
    people_only: bool = Query(False, description="Only rows with an identified person"),
) -> DecisionMakerListResponse:
    stmt = select(DecisionMaker)
    prov = _prov()
    if prov is not None:
        stmt = stmt.where(DecisionMaker.data_provenance == prov)
    if company:
        stmt = stmt.where(DecisionMaker.company_name.ilike(f"%{company}%"))
    if role_category is not None:
        stmt = stmt.where(DecisionMaker.role_category == role_category)
    if verification_status is not None:
        stmt = stmt.where(DecisionMaker.verification_status == verification_status)
    if people_only:
        stmt = stmt.where(DecisionMaker.full_name.is_not(None))
    rows = list(session.scalars(stmt.order_by(DecisionMaker.identity_confidence.desc())))
    total = len(rows)
    start = (page - 1) * page_size
    items = [DecisionMakerResponse.model_validate(r) for r in rows[start:start + page_size]]
    total_pages = (total + page_size - 1) // page_size if page_size else 0
    return DecisionMakerListResponse(items=items, total=total, page=page, page_size=page_size,
                                     total_pages=total_pages)


@router.get("/contacts/{contact_id}", response_model=DecisionMakerResponse, summary="Get a decision maker / contact")
def get_contact(contact_id: int, session: Session = Depends(get_session)) -> DecisionMakerResponse:
    row = session.get(DecisionMaker, contact_id)
    if row is None:
        raise NotFoundError(f"Contact {contact_id} not found.")
    return DecisionMakerResponse.model_validate(row)


def _company_decision_makers(session: Session, company_id: int, *, people: bool) -> list[DecisionMaker]:
    stmt = select(DecisionMaker).where(DecisionMaker.company_id == company_id)
    stmt = stmt.where(DecisionMaker.full_name.is_not(None)) if people else \
        stmt.where(DecisionMaker.business_email.is_not(None))
    return list(session.scalars(stmt.order_by(DecisionMaker.identity_confidence.desc())))


@router.get("/companies/{company_id}/decision-makers", response_model=DecisionMakerListResponse,
            summary="A company's verified decision makers (people)")
def company_decision_makers(company_id: int, session: Session = Depends(get_session)) -> DecisionMakerListResponse:
    if company_repo.get_company(session, company_id) is None:
        raise NotFoundError(f"Company {company_id} not found.")
    rows = _company_decision_makers(session, company_id, people=True)
    items = [DecisionMakerResponse.model_validate(r) for r in rows]
    return DecisionMakerListResponse(items=items, total=len(items), page=1,
                                     page_size=len(items) or 1, total_pages=1 if items else 0)


@router.get("/companies/{company_id}/contacts", response_model=DecisionMakerListResponse,
            summary="A company's business contacts")
def company_contacts(company_id: int, session: Session = Depends(get_session)) -> DecisionMakerListResponse:
    if company_repo.get_company(session, company_id) is None:
        raise NotFoundError(f"Company {company_id} not found.")
    rows = _company_decision_makers(session, company_id, people=False)
    items = [DecisionMakerResponse.model_validate(r) for r in rows]
    return DecisionMakerListResponse(items=items, total=len(items), page=1,
                                     page_size=len(items) or 1, total_pages=1 if items else 0)


@router.get("/leads/{lead_id}/stakeholders", response_model=LeadStakeholdersResponse,
            summary="Recommended stakeholder roles + verified people/contacts for a lead")
def lead_stakeholders(lead_id: int, session: Session = Depends(get_session)) -> LeadStakeholdersResponse:
    lead = get_lead(session, lead_id)
    if lead is None:
        raise NotFoundError(f"Lead with id {lead_id} was not found.")

    roles = recommend_for_lead(lead)
    role_items = [StakeholderRoleResponse(
        role=r.role, role_category=r.role_category, decision_maker_type=r.decision_maker_type,
        relevance_score=r.relevance_score, reason=r.reason, is_primary=r.is_primary,
    ) for r in roles.recommended_roles]

    # Verified people/contacts for the lead's resolved company (real data only).
    norm = lead.normalized_company_name or normalize_company_name(lead.company_name or "")
    company = session.scalar(select(Company).where(Company.normalized_name == norm))
    people, contacts = [], []
    if company is not None:
        people = [DecisionMakerResponse.model_validate(r)
                  for r in _company_decision_makers(session, company.id, people=True)
                  if r.verification_status in _VERIFIED]
        contacts = [DecisionMakerResponse.model_validate(r)
                    for r in _company_decision_makers(session, company.id, people=False)
                    if r.verification_status in _VERIFIED]

    readiness = classify_outreach_readiness(OutreachInputs(
        opportunity_verified=lead.verification_status in _VERIFIED,
        company_resolved=company is not None,
        role_identified=bool(role_items),
        has_verified_contact=bool(people or contacts),
        evidence_stale=lead.verification_status == VerificationStatus.STALE,
        contradicted=lead.verification_status == VerificationStatus.CONTRADICTED,
    ))
    return LeadStakeholdersResponse(
        lead_id=lead_id, company_name=lead.company_name, recommended_roles=role_items,
        recommendation_confidence=roles.recommendation_confidence,
        verified_decision_makers=people, business_contacts=contacts,
        outreach_readiness=readiness.readiness.value, outreach_reasons=readiness.reasons,
    )


@router.post("/companies/{company_id}/enrich", response_model=EnrichRunResponse,
             summary="Enrich a company from official sources (real, safe fetch)")
def enrich_company_endpoint(company_id: int, session: Session = Depends(get_session)) -> EnrichRunResponse:
    company = company_repo.get_company(session, company_id)
    if company is None:
        raise NotFoundError(f"Company {company_id} not found.")
    if not (company.primary_domain or company.website):
        raise ValidationError("Company has no official domain/website to enrich from.")
    summary = enrich_company(session, company, provenance=DataProvenance.REAL)
    return EnrichRunResponse(
        company_id=company_id, provider=summary.provider,
        people_found=summary.people_found, contacts_found=summary.contacts_found,
        people_accepted=summary.people_accepted, contacts_accepted=summary.contacts_accepted,
        duplicates=summary.duplicates, pages_fetched=summary.pages_fetched,
        message="OK" if not summary.errors else "; ".join(summary.errors[:3]),
    )
