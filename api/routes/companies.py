"""Company intelligence + entity-resolution endpoints. Logic lives in services."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from api.dependencies import get_session
from api.schemas import (
    CompanyListResponse,
    CompanyResponse,
    ResolutionCandidateResponse,
    ResolutionDecisionRequest,
)
from company import repository as repo
from company.service import CompanyIntelligenceService, CompanyResolutionService
from config.exceptions import NotFoundError, ValidationError
from config.settings import get_settings
from database.models import CompanyResolutionDecision, DataProvenance, VerificationStatus

logger = logging.getLogger(__name__)
router = APIRouter(tags=["companies"])
MAX_PAGE_SIZE = 100


def _default_provenance() -> DataProvenance | None:
    return None if get_settings().synthetic_leads_visible else DataProvenance.REAL


@router.get("/companies", response_model=CompanyListResponse, summary="List/search companies")
def list_companies(
    session: Session = Depends(get_session),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=MAX_PAGE_SIZE),
    search: str | None = Query(None),
    industry: str | None = Query(None),
    city: str | None = Query(None),
    verification_status: VerificationStatus | None = Query(None),
    sort_by: str = Query("updated_at"),
    sort_order: str = Query("desc"),
) -> CompanyListResponse:
    items, total = repo.search_companies(
        session, search=search, industry=industry, city=city,
        verification_status=verification_status, provenance=_default_provenance(),
        sort_by=sort_by, sort_order=sort_order, page=page, page_size=page_size,
    )
    total_pages = (total + page_size - 1) // page_size if page_size else 0
    return CompanyListResponse(
        items=[CompanyResponse.model_validate(c) for c in items],
        total=total, page=page, page_size=page_size, total_pages=total_pages,
    )


@router.get("/companies/{company_id}", response_model=CompanyResponse, summary="Get a company")
def get_company(company_id: int, session: Session = Depends(get_session)) -> CompanyResponse:
    company = repo.get_company(session, company_id)
    if company is None:
        raise NotFoundError(f"Company {company_id} not found.")
    return CompanyResponse.model_validate(company)


@router.get("/companies/{company_id}/intelligence", summary="Company intelligence profile")
def company_intelligence(company_id: int, session: Session = Depends(get_session)) -> dict:
    profile = CompanyIntelligenceService(session).profile(company_id)
    if profile is None:
        raise NotFoundError(f"Company {company_id} not found.")
    return profile


def _profile_or_404(session: Session, company_id: int) -> dict:
    profile = CompanyIntelligenceService(session).profile(company_id)
    if profile is None:
        raise NotFoundError(f"Company {company_id} not found.")
    return profile


@router.get("/companies/{company_id}/jobs", summary="Company canonical jobs")
def company_jobs(company_id: int, session: Session = Depends(get_session)) -> dict:
    company = repo.get_company(session, company_id)
    if company is None:
        raise NotFoundError(f"Company {company_id} not found.")
    jobs = repo.company_jobs(session, company.normalized_name, company.data_provenance)
    return {"canonical_job_count": len(jobs), "jobs": [
        {"id": j.id, "title": j.original_job_title, "city": j.city, "technologies": j.technologies,
         "published_at": j.published_at.isoformat() if j.published_at else None,
         "source_count": j.source_count, "primary_source": j.primary_source} for j in jobs[:200]]}


@router.get("/companies/{company_id}/signals", summary="Company business signals")
def company_signals(company_id: int, session: Session = Depends(get_session)) -> dict:
    return {"signals": _profile_or_404(session, company_id)["signals"]}


@router.get("/companies/{company_id}/opportunities", summary="Company opportunities")
def company_opportunities(company_id: int, session: Session = Depends(get_session)) -> dict:
    profile = _profile_or_404(session, company_id)
    return {"opportunity": profile["opportunity"], "related_leads": profile["related_leads"]}


@router.get("/companies/{company_id}/evidence", summary="Company evidence summary")
def company_evidence(company_id: int, session: Session = Depends(get_session)) -> dict:
    return _profile_or_404(session, company_id)["evidence"]


@router.get("/companies/{company_id}/history", summary="Company intelligence history")
def company_history(company_id: int, session: Session = Depends(get_session)) -> dict:
    company = repo.get_company(session, company_id)
    if company is None:
        raise NotFoundError(f"Company {company_id} not found.")
    events = repo.company_history(session, company_id)
    return {"events": [
        {"event_type": e.event_type, "description": e.description,
         "created_at": e.created_at.isoformat() if e.created_at else None} for e in events]}


@router.get("/company-resolution/review", response_model=list[ResolutionCandidateResponse],
            summary="Pending entity-resolution reviews")
def resolution_review(session: Session = Depends(get_session)) -> list[ResolutionCandidateResponse]:
    cands = repo.list_review_candidates(session, provenance=_default_provenance())
    return [ResolutionCandidateResponse.model_validate(c) for c in cands]


@router.post("/company-resolution/{candidate_id}/resolve", summary="Resolve an entity-resolution review")
def resolve_review(candidate_id: int, body: ResolutionDecisionRequest,
                   session: Session = Depends(get_session)) -> dict:
    try:
        decision = CompanyResolutionDecision(body.decision.upper())
    except ValueError as exc:
        raise ValidationError(f"Invalid decision '{body.decision}'. Use MERGE | KEEP_SEPARATE | IGNORE.") from exc
    ok = CompanyResolutionService(session).resolve_review(candidate_id, decision)
    if not ok:
        raise NotFoundError(f"Resolution candidate {candidate_id} not found.")
    return {"candidate_id": candidate_id, "decision": decision.value}
