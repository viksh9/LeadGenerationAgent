"""Lead endpoints: direct CRUD, listing/search, and the analysis pipeline.

Handlers are thin — validation is delegated to Pydantic schemas, querying to the
repository, and intelligence to the LeadAnalysisPipeline. No SQL or scoring logic
lives here.
"""

from __future__ import annotations

import logging
from enum import Enum

from fastapi import APIRouter, Depends, Query, Response, status
from sqlalchemy.orm import Session

from api.dependencies import get_session
from api.schemas import (
    LeadAnalyzeRequest,
    LeadCreate,
    LeadListResponse,
    LeadResponse,
    LeadUpdate,
)
from config.exceptions import NotFoundError
from database.models import LeadPriority, LeadStatus, SignalType
from database.repository import (
    create_lead,
    delete_lead,
    get_lead,
    query_leads,
    update_lead,
)
from intelligence.lead_pipeline import LeadAnalysisPipeline, LeadAnalysisResult

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/leads", tags=["leads"])

pipeline = LeadAnalysisPipeline()

MAX_PAGE_SIZE = 100


class SortField(str, Enum):
    lead_score = "lead_score"
    created_at = "created_at"
    updated_at = "updated_at"
    signal_date = "signal_date"
    company_name = "company_name"


class SortOrder(str, Enum):
    asc = "asc"
    desc = "desc"


@router.post(
    "",
    response_model=LeadResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a lead",
    description="Create a lead directly from client-supplied fields (no intelligence pipeline).",
)
def create_lead_endpoint(payload: LeadCreate, session: Session = Depends(get_session)) -> LeadResponse:
    lead = create_lead(session, **payload.model_dump())
    logger.info("lead_created lead_id=%s company=%s", lead.id, lead.company_name)
    return LeadResponse.model_validate(lead)


@router.post(
    "/analyze",
    response_model=LeadAnalysisResult,
    status_code=status.HTTP_201_CREATED,
    summary="Analyze a raw lead",
    description=(
        "Run the full analysis pipeline (signals → opportunity → score → POC → pitch) "
        "and persist the calculated lead. Returns 201 for a new lead, 200 when an "
        "existing lead is re-analyzed."
    ),
)
def analyze_lead_endpoint(
    payload: LeadAnalyzeRequest,
    response: Response,
    session: Session = Depends(get_session),
) -> LeadAnalysisResult:
    logger.info("lead_analyze_requested company=%s", payload.company_name)
    result = pipeline.analyze(payload, session=session, persist=True)
    if result.already_existed:
        response.status_code = status.HTTP_200_OK
    logger.info("lead_analyzed lead_id=%s existed=%s", result.lead_id, result.already_existed)
    return result


@router.get(
    "",
    response_model=LeadListResponse,
    summary="List leads",
    description="Filter, search, sort, and paginate leads. Defaults to highest lead_score first.",
)
def list_leads_endpoint(
    session: Session = Depends(get_session),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=MAX_PAGE_SIZE),
    search: str | None = Query(None, description="Case-insensitive search over company/signal/project"),
    industry: str | None = Query(None),
    location: str | None = Query(None),
    signal_type: SignalType | None = Query(None),
    lead_priority: LeadPriority | None = Query(None),
    status_filter: LeadStatus | None = Query(None, alias="status"),
    min_score: float | None = Query(None, ge=0, le=100),
    max_score: float | None = Query(None, ge=0, le=100),
    technology: str | None = Query(None),
    sort_by: SortField = Query(SortField.lead_score),
    sort_order: SortOrder = Query(SortOrder.desc),
) -> LeadListResponse:
    items, total = query_leads(
        session,
        search=search,
        industry=industry,
        location=location,
        signal_type=signal_type,
        lead_priority=lead_priority,
        status=status_filter,
        min_score=min_score,
        max_score=max_score,
        technology=technology,
        sort_by=sort_by.value,
        sort_order=sort_order.value,
        page=page,
        page_size=page_size,
    )
    total_pages = (total + page_size - 1) // page_size if page_size else 0
    return LeadListResponse(
        items=[LeadResponse.model_validate(lead) for lead in items],
        total=total,
        page=page,
        page_size=page_size,
        total_pages=total_pages,
    )


@router.get(
    "/{lead_id}",
    response_model=LeadResponse,
    summary="Get a lead",
    responses={404: {"description": "Lead not found"}},
)
def get_lead_endpoint(lead_id: int, session: Session = Depends(get_session)) -> LeadResponse:
    lead = get_lead(session, lead_id)
    if lead is None:
        logger.info("lead_not_found lead_id=%s", lead_id)
        raise NotFoundError(f"Lead with id {lead_id} was not found.")
    return LeadResponse.model_validate(lead)


@router.put(
    "/{lead_id}",
    response_model=LeadResponse,
    summary="Update a lead",
    description="Update editable fields. Calculated intelligence fields cannot be set by clients.",
    responses={404: {"description": "Lead not found"}},
)
def update_lead_endpoint(
    lead_id: int, payload: LeadUpdate, session: Session = Depends(get_session)
) -> LeadResponse:
    lead = update_lead(session, lead_id, **payload.model_dump(exclude_unset=True))
    if lead is None:
        raise NotFoundError(f"Lead with id {lead_id} was not found.")
    logger.info("lead_updated lead_id=%s", lead_id)
    return LeadResponse.model_validate(lead)


@router.delete(
    "/{lead_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a lead",
    responses={404: {"description": "Lead not found"}},
)
def delete_lead_endpoint(lead_id: int, session: Session = Depends(get_session)) -> Response:
    if not delete_lead(session, lead_id):
        raise NotFoundError(f"Lead with id {lead_id} was not found.")
    logger.info("lead_deleted lead_id=%s", lead_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
