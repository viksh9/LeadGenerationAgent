"""Official company career / ATS source endpoints.

Discovery, listing, connectivity checks, and on-demand collection for
company-controlled hiring sources (Greenhouse, Lever, official career pages).
Real, safe operations only — no unrestricted URL fetching, no fabricated boards.
Business logic lives in the collector/discovery/registry services.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from api.dependencies import get_session
from api.schemas import (
    CareerSourceCollectResponse,
    CareerSourceListResponse,
    CareerSourceResponse,
    DiscoverCareerSourceResponse,
    SourceCheckResponse,
)
from collectors import career_source_registry as csr
from collectors.base import FetchRequest, HealthStatus
from collectors.company.career_source_discovery import discover_career_source
from collectors.errors import CollectorError
from collectors.service import JobCollectionService
from company import repository as company_repo
from config.exceptions import NotFoundError, ValidationError
from database.models import AtsProvider, CareerSourceStatus, DataProvenance, utcnow
from ingestion.job_pipeline import run_company_pipeline

logger = logging.getLogger(__name__)
router = APIRouter(tags=["career-sources"])

# HealthStatus -> CareerSourceStatus (persisted)
_HEALTH_TO_CAREER = {
    HealthStatus.HEALTHY: CareerSourceStatus.CONNECTED,
    HealthStatus.DEGRADED: CareerSourceStatus.CONNECTED,
    HealthStatus.NOT_CONFIGURED: CareerSourceStatus.DISCOVERY_REQUIRED,
    HealthStatus.AUTHENTICATION_FAILED: CareerSourceStatus.ERROR,
    HealthStatus.RATE_LIMITED: CareerSourceStatus.ERROR,
    HealthStatus.UNAVAILABLE: CareerSourceStatus.ERROR,
    HealthStatus.RESTRICTED: CareerSourceStatus.ERROR,
}


def _build_ats_collector(provider: AtsProvider, board: str):
    """Construct the provider collector bound to a specific board/site."""
    from collectors.source_registry import get_registry

    if provider is AtsProvider.GREENHOUSE:
        from collectors.ats.greenhouse import GreenhouseCollector, GreenhouseConfig

        return GreenhouseCollector(get_registry().get("greenhouse"),
                                   config=GreenhouseConfig(boards=[board]))
    if provider is AtsProvider.LEVER:
        from collectors.ats.lever import LeverCollector, LeverConfig

        return LeverCollector(get_registry().get("lever"), config=LeverConfig(sites=[board]))
    raise ValidationError(f"No runnable ATS collector for provider {provider.value}.")


@router.get("/career-sources", response_model=CareerSourceListResponse, summary="List career sources")
def list_career_sources_endpoint(session: Session = Depends(get_session)) -> CareerSourceListResponse:
    rows = csr.list_career_sources(session)
    return CareerSourceListResponse(
        items=[CareerSourceResponse.model_validate(r) for r in rows], total=len(rows)
    )


@router.get("/career-sources/{source_id}", response_model=CareerSourceResponse, summary="Get a career source")
def get_career_source_endpoint(source_id: int, session: Session = Depends(get_session)) -> CareerSourceResponse:
    row = csr.get_career_source(session, source_id)
    if row is None:
        raise NotFoundError(f"Career source {source_id} not found.")
    return CareerSourceResponse.model_validate(row)


@router.get("/companies/{company_id}/career-sources", response_model=CareerSourceListResponse,
            summary="List a company's career sources")
def company_career_sources_endpoint(company_id: int, session: Session = Depends(get_session)) -> CareerSourceListResponse:
    rows = csr.list_for_company(session, company_id)
    return CareerSourceListResponse(
        items=[CareerSourceResponse.model_validate(r) for r in rows], total=len(rows)
    )


@router.post("/companies/{company_id}/discover-career-source", response_model=DiscoverCareerSourceResponse,
             summary="Discover + verify a company's official ATS/career source")
def discover_career_source_endpoint(
    company_id: int, session: Session = Depends(get_session)
) -> DiscoverCareerSourceResponse:
    company = company_repo.get_company(session, company_id)
    if company is None:
        raise NotFoundError(f"Company {company_id} not found.")

    # If the company has no known domain/website, derive the official domain from
    # real signals (company name + a real lead's source URL) before probing (§4).
    domain = company.primary_domain
    if not domain and not company.website:
        from collectors.company.domain_discovery import CompanyDomainDiscoveryService
        from database.models import Lead
        from sqlalchemy import select
        lead = session.execute(
            select(Lead).where(Lead.normalized_company_name == company.normalized_name)
            .order_by(Lead.updated_at.desc()).limit(1)
        ).scalars().first()
        dd = CompanyDomainDiscoveryService().discover(
            company_name=company.canonical_name,
            source_url=(lead.source_url if lead else None),
        )
        if dd.selected_domain and dd.status in ("VERIFIED", "POSSIBLE"):
            domain = dd.selected_domain

    result = discover_career_source(
        company_id=company.id, company_name=company.canonical_name,
        domain=domain, website=company.website,
    )
    row = csr.register_from_discovery(session, result)
    return DiscoverCareerSourceResponse(
        company_id=company.id, company_name=company.canonical_name,
        found=bool(result.provider and result.board_identifier), verified=result.verified,
        provider=result.provider.value if result.provider else None,
        board_identifier=result.board_identifier, careers_url=result.careers_url,
        discovery_method=result.discovery_method, detail=result.detail,
        career_source=CareerSourceResponse.model_validate(row) if row else None,
    )


@router.post("/career-sources/{source_id}/check", response_model=SourceCheckResponse,
             summary="Check a career source connection (real request)")
def check_career_source_endpoint(source_id: int, session: Session = Depends(get_session)) -> SourceCheckResponse:
    row = csr.get_career_source(session, source_id)
    if row is None:
        raise NotFoundError(f"Career source {source_id} not found.")
    if not row.board_identifier:
        raise ValidationError("Career source has no board identifier to check (DISCOVERY_REQUIRED).")
    collector = _build_ats_collector(row.ats_provider, row.board_identifier)
    health = collector.health_check()
    status = _HEALTH_TO_CAREER.get(health.status, CareerSourceStatus.ERROR)
    row.status = status
    row.last_checked_at = utcnow()
    if status is CareerSourceStatus.CONNECTED:
        row.last_success_at = utcnow()
        row.last_error = None
    else:
        row.last_error = (health.message or status.value)[:512]
    session.commit()
    return SourceCheckResponse(
        source_id=str(source_id), connection_status=status.value,
        message=health.message, performed_request=health.status is not HealthStatus.NOT_CONFIGURED,
        checked_at=utcnow(),
    )


@router.post("/career-sources/{source_id}/collect", response_model=CareerSourceCollectResponse,
             summary="Collect real jobs from a career source")
def collect_career_source_endpoint(source_id: int, session: Session = Depends(get_session)) -> CareerSourceCollectResponse:
    row = csr.get_career_source(session, source_id)
    if row is None:
        raise NotFoundError(f"Career source {source_id} not found.")
    if not row.board_identifier:
        raise ValidationError("Career source has no board identifier to collect (DISCOVERY_REQUIRED).")

    collector = _build_ats_collector(row.ats_provider, row.board_identifier)
    try:
        summary = JobCollectionService(session).collect(
            collector, [FetchRequest(board=row.board_identifier)]
        )
    except CollectorError as exc:
        row.status = CareerSourceStatus.ERROR
        row.last_error = str(exc)[:512]
        session.commit()
        return CareerSourceCollectResponse(
            source_id=source_id, provider=row.ats_provider.value,
            board_identifier=row.board_identifier, status=CareerSourceStatus.ERROR.value,
            message=str(exc),
        )

    result = run_company_pipeline(session, provenance=DataProvenance.REAL)
    # A real request succeeded → mark CONNECTED.
    csr.register_career_source(
        session, ats_provider=row.ats_provider, board_identifier=row.board_identifier,
        status=CareerSourceStatus.CONNECTED, company_name=row.company_name,
    )
    return CareerSourceCollectResponse(
        source_id=source_id, provider=row.ats_provider.value, board_identifier=row.board_identifier,
        status=CareerSourceStatus.CONNECTED.value, requests=summary.requests,
        records_fetched=summary.fetched, records_persisted=summary.accepted,
        canonical_jobs_created=result.dedup.canonical_created,
        leads_created=result.companies.created, leads_updated=result.companies.updated,
        message="OK",
    )
