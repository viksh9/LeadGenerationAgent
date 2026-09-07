"""Business-signal, tender, and company-timeline endpoints (real stored data only).

Read-only views over BusinessSignal / TenderRecord and a chronological company
timeline. Empty when no real data exists — never fabricated.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from api.dependencies import get_session
from api.schemas import (
    SignalListResponse,
    SignalResponse,
    TenderListResponse,
    TenderResponse,
    TimelineEventResponse,
    TimelineResponse,
)
from collectors.raw_record import normalize_company_name
from company import repository as company_repo
from config.exceptions import NotFoundError
from config.settings import get_settings
from database.models import (
    BusinessSignal,
    BusinessSignalType,
    DataProvenance,
    TenderRecord,
    TenderStatus,
)
from intelligence.company_timeline import build_company_timeline

logger = logging.getLogger(__name__)
router = APIRouter(tags=["signals"])
MAX_PAGE_SIZE = 100


def _prov() -> DataProvenance | None:
    return None if get_settings().synthetic_leads_visible else DataProvenance.REAL


def _signal_response(sig: BusinessSignal) -> SignalResponse:
    return SignalResponse(
        id=sig.id, company_id=sig.company_id, company_name=sig.company_name,
        signal_type=sig.signal_type.value, signal_title=sig.signal_title,
        signal_description=sig.signal_description, signal_url=sig.signal_url,
        published_at=sig.published_at, technologies=list(sig.technology_terms or []),
        location=sig.location, signal_strength=sig.signal_strength.value,
        source_id=sig.source_id, source_count=sig.source_count,
        evidence_confidence=sig.evidence_confidence,
        commercial_intent=sig.commercial_intent.value if sig.commercial_intent else "UNKNOWN",
        data_provenance=sig.data_provenance.value,
    )


@router.get("/signals", response_model=SignalListResponse, summary="List business signals")
def list_signals(
    session: Session = Depends(get_session),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=MAX_PAGE_SIZE),
    signal_type: BusinessSignalType | None = Query(None),
    company: str | None = Query(None, description="Company name (normalized match)"),
    technology: str | None = Query(None),
    source: str | None = Query(None),
) -> SignalListResponse:
    conditions = []
    prov = _prov()
    if prov is not None:
        conditions.append(BusinessSignal.data_provenance == prov)
    if signal_type is not None:
        conditions.append(BusinessSignal.signal_type == signal_type)
    if company:
        conditions.append(BusinessSignal.normalized_company_name == normalize_company_name(company))
    if source:
        conditions.append(BusinessSignal.source_id == source)

    base = select(BusinessSignal)
    for c in conditions:
        base = base.where(c)
    rows = list(session.scalars(base.order_by(BusinessSignal.published_at.desc().nullslast())))
    if technology:
        tl = technology.lower()
        rows = [r for r in rows if any(tl == t.lower() for t in (r.technology_terms or []))]
    total = len(rows)
    start = (page - 1) * page_size
    items = [_signal_response(r) for r in rows[start:start + page_size]]
    total_pages = (total + page_size - 1) // page_size if page_size else 0
    return SignalListResponse(items=items, total=total, page=page, page_size=page_size,
                              total_pages=total_pages)


@router.get("/signals/{signal_id}", response_model=SignalResponse, summary="Get a business signal")
def get_signal(signal_id: int, session: Session = Depends(get_session)) -> SignalResponse:
    sig = session.get(BusinessSignal, signal_id)
    if sig is None:
        raise NotFoundError(f"Signal {signal_id} not found.")
    return _signal_response(sig)


@router.get("/companies/{company_id}/signals-detail", response_model=SignalListResponse,
            summary="A company's business signals (full detail)")
def company_signals_detail(company_id: int, session: Session = Depends(get_session)) -> SignalListResponse:
    company = company_repo.get_company(session, company_id)
    if company is None:
        raise NotFoundError(f"Company {company_id} not found.")
    rows = company_repo.company_signals(session, company.normalized_name, _prov() or DataProvenance.REAL)
    items = [_signal_response(r) for r in rows]
    return SignalListResponse(items=items, total=len(items), page=1, page_size=len(items) or 1,
                              total_pages=1 if items else 0)


# --------------------------------------------------------------------------- #
# Tenders
# --------------------------------------------------------------------------- #
@router.get("/tenders", response_model=TenderListResponse, summary="List tenders")
def list_tenders(
    session: Session = Depends(get_session),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=MAX_PAGE_SIZE),
    status: TenderStatus | None = Query(None),
    technology: str | None = Query(None),
    organization: str | None = Query(None),
    category: str | None = Query(None),
) -> TenderListResponse:
    prov = _prov()
    base = select(TenderRecord)
    if prov is not None:
        base = base.where(TenderRecord.data_provenance == prov)
    if status is not None:
        base = base.where(TenderRecord.tender_status == status)
    if organization:
        base = base.where(TenderRecord.organization_name.ilike(f"%{organization}%"))
    if category:
        base = base.where(TenderRecord.category.ilike(f"%{category}%"))
    rows = list(session.scalars(base.order_by(TenderRecord.publication_date.desc().nullslast())))
    if technology:
        tl = technology.lower()
        rows = [r for r in rows if any(tl == t.lower() for t in (r.technologies or []))]
    total = len(rows)
    start = (page - 1) * page_size
    items = [TenderResponse.model_validate(r) for r in rows[start:start + page_size]]
    total_pages = (total + page_size - 1) // page_size if page_size else 0
    return TenderListResponse(items=items, total=total, page=page, page_size=page_size,
                              total_pages=total_pages)


@router.get("/tenders/{tender_id}", response_model=TenderResponse, summary="Get a tender")
def get_tender(tender_id: int, session: Session = Depends(get_session)) -> TenderResponse:
    t = session.get(TenderRecord, tender_id)
    if t is None:
        raise NotFoundError(f"Tender {tender_id} not found.")
    return TenderResponse.model_validate(t)


@router.get("/companies/{company_id}/tenders", response_model=TenderListResponse,
            summary="A company's tenders")
def company_tenders(company_id: int, session: Session = Depends(get_session)) -> TenderListResponse:
    company = company_repo.get_company(session, company_id)
    if company is None:
        raise NotFoundError(f"Company {company_id} not found.")
    norm = company.normalized_name
    rows = [
        t for t in session.scalars(select(TenderRecord)).all()
        if t.company_id == company_id
        or normalize_company_name(t.organization_name or "") == norm
    ]
    items = [TenderResponse.model_validate(r) for r in rows]
    return TenderListResponse(items=items, total=len(items), page=1, page_size=len(items) or 1,
                              total_pages=1 if items else 0)


@router.get("/companies/{company_id}/timeline", response_model=TimelineResponse,
            summary="A company's business-event timeline")
def company_timeline(company_id: int, session: Session = Depends(get_session)) -> TimelineResponse:
    company = company_repo.get_company(session, company_id)
    if company is None:
        raise NotFoundError(f"Company {company_id} not found.")
    events = build_company_timeline(session, normalized_name=company.normalized_name,
                                    provenance=_prov() or DataProvenance.REAL)
    return TimelineResponse(
        company_id=company_id,
        events=[TimelineEventResponse(**e.as_dict()) for e in events],
        total=len(events),
    )
