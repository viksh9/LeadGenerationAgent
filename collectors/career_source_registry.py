"""Persistence for discovered official company career / ATS sources.

Records a legitimately-identified ATS board (Greenhouse board_token, Lever site)
so a company-specific collector can be activated and tracked. A board is only
registered after it is actually known/used — never fabricated. Status becomes
CONNECTED only after a real public request has succeeded.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from database.models import AtsProvider, CareerSourceStatus, CompanyCareerSource

# source_id -> ATS provider enum
_PROVIDER_BY_SOURCE = {
    "greenhouse": AtsProvider.GREENHOUSE,
    "lever": AtsProvider.LEVER,
}


def provider_for(source_id: str) -> Optional[AtsProvider]:
    return _PROVIDER_BY_SOURCE.get(source_id)


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def register_career_source(
    session: Session,
    *,
    ats_provider: AtsProvider,
    board_identifier: str,
    status: CareerSourceStatus = CareerSourceStatus.CONNECTED,
    company_name: Optional[str] = None,
    careers_url: Optional[str] = None,
    discovery_method: str = "collector_run",
    error: Optional[str] = None,
) -> CompanyCareerSource:
    """Upsert a career source by (provider, board_identifier). Idempotent."""
    row = session.scalar(
        select(CompanyCareerSource).where(
            CompanyCareerSource.ats_provider == ats_provider,
            CompanyCareerSource.board_identifier == board_identifier,
        )
    )
    now = _now()
    if row is None:
        row = CompanyCareerSource(
            ats_provider=ats_provider, board_identifier=board_identifier,
            discovery_method=discovery_method,
        )
        session.add(row)
    row.status = status
    row.enabled = status in (CareerSourceStatus.CONFIGURED, CareerSourceStatus.CONNECTED)
    row.last_checked_at = now
    if status is CareerSourceStatus.CONNECTED:
        row.last_success_at = now
        row.last_error = None
    if company_name and not row.company_name:
        row.company_name = company_name
    if careers_url and not row.careers_url:
        row.careers_url = careers_url
    if error:
        row.last_error = error[:512]
    session.commit()
    return row


def list_career_sources(session: Session) -> list[CompanyCareerSource]:
    return list(session.scalars(select(CompanyCareerSource).order_by(CompanyCareerSource.id)))


def get_career_source(session: Session, source_id: int) -> Optional[CompanyCareerSource]:
    return session.get(CompanyCareerSource, source_id)


def list_for_company(session: Session, company_id: int) -> list[CompanyCareerSource]:
    return list(session.scalars(
        select(CompanyCareerSource).where(CompanyCareerSource.company_id == company_id)
        .order_by(CompanyCareerSource.id)
    ))


def register_from_discovery(session: Session, result) -> Optional[CompanyCareerSource]:
    """Persist a verified DiscoveryResult as a CONFIGURED career source.

    Returns the row, or None if discovery found nothing (never fabricates a board).
    Status is CONFIGURED (relationship verified) — CONNECTED only after a real
    collection succeeds (register_career_source at collect time).
    """
    if not (result.verified and result.provider and result.board_identifier):
        return None
    row = register_career_source(
        session,
        ats_provider=result.provider,
        board_identifier=result.board_identifier,
        status=CareerSourceStatus.CONFIGURED,
        company_name=result.company_name,
        careers_url=result.careers_url,
        discovery_method=result.discovery_method or "discovery",
    )
    if result.company_id and not row.company_id:
        row.company_id = result.company_id
        session.commit()
    return row
