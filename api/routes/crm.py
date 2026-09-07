"""CRM endpoints (§4, §21, §22, §23, §24, §29, §33, §36).

Read endpoints allow any role; mutations require SALES (or ADMIN). Every number is
derived from real records — analytics return INSUFFICIENT_DATA / NOT_AVAILABLE
rather than fabricate. Lead status changes go through the validated lifecycle.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from api.dependencies import get_session
from api.schemas import (
    ActivityCreateRequest,
    CRMActivityListResponse,
    CRMActivityResponse,
    CRMAnalyticsResponse,
    FollowUpStatusUpdate,
    FollowUpTaskListResponse,
    FollowUpTaskResponse,
    LeadStatusHistoryResponse,
    LeadStatusTransitionRequest,
    LeadTimelineResponse,
    NextBestActionResponse,
    PipelineBoardResponse,
    PipelineStageColumn,
    SalesOpportunityCreate,
    SalesOpportunityListResponse,
    SalesOpportunityResponse,
    SalesStageUpdate,
    TimelineItem,
)
from api.security import require_role
from config.exceptions import NotFoundError, ValidationError
from crm.activities import CRMActivityService
from crm.analytics import compute_crm_analytics
from crm.followups import FollowUpService
from crm.lifecycle import LeadLifecycleService
from crm.nba import next_best_action
from crm.pipeline import SalesPipelineService
from database.models import (
    ActivityType,
    FollowUpStatus,
    FollowUpTask,
    Lead,
    LeadChangeEvent,
    LeadStatus,
    SalesOpportunity,
    SalesStage,
    UserRole,
)

router = APIRouter(tags=["crm"])

_sales = require_role(UserRole.SALES)
_viewer = require_role(UserRole.VIEWER, UserRole.RESEARCHER, UserRole.SALES)


# ---- Lead lifecycle -------------------------------------------------------- #
@router.post("/leads/{lead_id}/transition", response_model=LeadStatusHistoryResponse,
             summary="Transition a lead's status (validated, audited)")
def transition_lead(lead_id: int, payload: LeadStatusTransitionRequest,
                    session: Session = Depends(get_session), role=Depends(_sales)) -> LeadStatusHistoryResponse:
    svc = LeadLifecycleService(session)
    try:
        svc.transition(lead_id, payload.new_status, changed_by="human", reason=payload.reason,
                       source="MANUAL")
    except ValueError as exc:
        raise ValidationError(str(exc)) from exc
    session.commit()
    latest = svc.history(lead_id)[-1]
    return LeadStatusHistoryResponse.model_validate(latest)


@router.get("/leads/{lead_id}/status-history",
            response_model=list[LeadStatusHistoryResponse], summary="Lead status history")
def lead_status_history(lead_id: int, session: Session = Depends(get_session),
                        role=Depends(_viewer)) -> list[LeadStatusHistoryResponse]:
    rows = LeadLifecycleService(session).history(lead_id)
    return [LeadStatusHistoryResponse.model_validate(r) for r in rows]


@router.get("/leads/{lead_id}/next-best-action", response_model=NextBestActionResponse,
            summary="Deterministic next best action from real state")
def lead_nba(lead_id: int, session: Session = Depends(get_session),
             role=Depends(_viewer)) -> NextBestActionResponse:
    lead = session.get(Lead, lead_id)
    if lead is None:
        raise NotFoundError(f"Lead {lead_id} not found.")
    return NextBestActionResponse(lead_id=lead_id, next_best_action=next_best_action(session, lead))


# ---- Activities + timeline ------------------------------------------------- #
@router.get("/leads/{lead_id}/activities", response_model=CRMActivityListResponse,
            summary="CRM activities for a lead")
def lead_activities(lead_id: int, session: Session = Depends(get_session),
                    role=Depends(_viewer)) -> CRMActivityListResponse:
    rows = CRMActivityService(session).list_for_lead(lead_id)
    return CRMActivityListResponse(items=[CRMActivityResponse.model_validate(r) for r in rows],
                                   total=len(rows))


@router.post("/activities", response_model=CRMActivityResponse, summary="Log a manual CRM activity")
def create_activity(payload: ActivityCreateRequest, session: Session = Depends(get_session),
                    role=Depends(_sales)) -> CRMActivityResponse:
    try:
        atype = ActivityType(payload.activity_type)
    except ValueError as exc:
        raise ValidationError(f"Invalid activity_type '{payload.activity_type}'.") from exc
    activity = CRMActivityService(session).log(
        activity_type=atype, lead_id=payload.lead_id, company_id=payload.company_id,
        contact_id=payload.contact_id, opportunity_id=payload.opportunity_id,
        subject=payload.subject, body_reference=payload.body_reference, is_system_event=False,
        created_by="human",
    )
    session.commit()
    return CRMActivityResponse.model_validate(activity)


@router.get("/leads/{lead_id}/timeline", response_model=LeadTimelineResponse,
            summary="Chronological timeline: system events + human activities (§36)")
def lead_timeline(lead_id: int, session: Session = Depends(get_session),
                  role=Depends(_viewer)) -> LeadTimelineResponse:
    items: list[TimelineItem] = []
    for a in CRMActivityService(session).list_for_lead(lead_id, limit=200):
        items.append(TimelineItem(
            kind="SYSTEM_EVENT" if a.is_system_event else "HUMAN_ACTIVITY",
            category="ACTIVITY",
            event_type=(a.activity_type.value if hasattr(a.activity_type, "value") else str(a.activity_type)),
            title=a.subject or "", detail=a.body_reference, occurred_at=a.occurred_at, source=a.source,
        ))
    change_events = session.execute(
        select(LeadChangeEvent).where(LeadChangeEvent.lead_id == lead_id)
        .order_by(LeadChangeEvent.detected_at.desc()).limit(100)
    ).scalars().all()
    for e in change_events:
        items.append(TimelineItem(
            kind="SYSTEM_EVENT", category="CHANGE", event_type=e.change_type,
            title=e.summary or e.change_type, detail=(f"{e.old_value} → {e.new_value}"
                                                      if e.old_value or e.new_value else None),
            occurred_at=e.detected_at, source="MONITORING",
        ))
    items.sort(key=lambda i: i.occurred_at, reverse=True)
    return LeadTimelineResponse(lead_id=lead_id, items=items, total=len(items))


# ---- Sales pipeline -------------------------------------------------------- #
@router.get("/sales-opportunities", response_model=SalesOpportunityListResponse,
            summary="List managed sales opportunities")
def list_sales_opportunities(stage: str | None = None, company_id: int | None = None,
                             limit: int = Query(100, le=500), offset: int = 0,
                             session: Session = Depends(get_session),
                             role=Depends(_viewer)) -> SalesOpportunityListResponse:
    stage_enum = _parse_stage(stage) if stage else None
    rows = SalesPipelineService(session).list(stage=stage_enum, company_id=company_id,
                                              limit=limit, offset=offset)
    total = int(session.execute(select(func.count(SalesOpportunity.id))).scalar() or 0)
    return SalesOpportunityListResponse(
        items=[SalesOpportunityResponse.model_validate(r) for r in rows], total=total)


@router.get("/pipeline/board", response_model=PipelineBoardResponse, summary="Pipeline board by stage")
def pipeline_board(session: Session = Depends(get_session), role=Depends(_viewer)) -> PipelineBoardResponse:
    svc = SalesPipelineService(session)
    columns = []
    total = 0
    for stage in SalesStage:
        rows = svc.list(stage=stage, limit=100)
        total += len(rows)
        columns.append(PipelineStageColumn(
            stage=stage.value, count=len(rows),
            opportunities=[SalesOpportunityResponse.model_validate(r) for r in rows],
        ))
    return PipelineBoardResponse(columns=columns, total=total)


@router.post("/sales-opportunities", response_model=SalesOpportunityResponse,
             summary="Create a managed sales opportunity")
def create_sales_opportunity(payload: SalesOpportunityCreate, session: Session = Depends(get_session),
                             role=Depends(_sales)) -> SalesOpportunityResponse:
    opp = SalesPipelineService(session).create(
        title=payload.title, company_id=payload.company_id, lead_id=payload.lead_id,
        opportunity_type=payload.opportunity_type, description=payload.description,
        estimated_team_scale=payload.estimated_team_scale, estimated_value=payload.estimated_value,
        estimated_value_currency=payload.estimated_value_currency, value_source=payload.value_source,
        actor="human",
    )
    session.commit()
    return SalesOpportunityResponse.model_validate(opp)


@router.post("/sales-opportunities/{opp_id}/stage", response_model=SalesOpportunityResponse,
             summary="Change opportunity stage (human-approved)")
def set_opportunity_stage(opp_id: int, payload: SalesStageUpdate,
                          session: Session = Depends(get_session),
                          role=Depends(_sales)) -> SalesOpportunityResponse:
    stage = _parse_stage(payload.stage)
    opp = SalesPipelineService(session).set_stage(opp_id, stage, actor="human", reason=payload.reason)
    session.commit()
    return SalesOpportunityResponse.model_validate(opp)


@router.post("/opportunity-candidates/{candidate_id}/promote", response_model=SalesOpportunityResponse,
             summary="Promote an analytical candidate to a managed opportunity")
def promote_candidate(candidate_id: int, session: Session = Depends(get_session),
                      role=Depends(_sales)) -> SalesOpportunityResponse:
    opp = SalesPipelineService(session).promote_from_candidate(candidate_id, actor="human")
    session.commit()
    return SalesOpportunityResponse.model_validate(opp)


# ---- Follow-ups ------------------------------------------------------------ #
@router.get("/follow-ups", response_model=FollowUpTaskListResponse, summary="List follow-up tasks")
def list_followups(status: str | None = None, lead_id: int | None = None,
                   session: Session = Depends(get_session),
                   role=Depends(_viewer)) -> FollowUpTaskListResponse:
    status_enum = None
    if status:
        try:
            status_enum = FollowUpStatus(status.upper())
        except ValueError as exc:
            raise ValidationError(f"Invalid follow-up status '{status}'.") from exc
    rows = FollowUpService(session).list(status=status_enum, lead_id=lead_id)
    total = int(session.execute(select(func.count(FollowUpTask.id))).scalar() or 0)
    return FollowUpTaskListResponse(items=[FollowUpTaskResponse.model_validate(r) for r in rows],
                                    total=total)


@router.post("/follow-ups/{task_id}/status", response_model=FollowUpTaskResponse,
             summary="Update a follow-up task status")
def set_followup_status(task_id: int, payload: FollowUpStatusUpdate,
                        session: Session = Depends(get_session),
                        role=Depends(_sales)) -> FollowUpTaskResponse:
    try:
        status_enum = FollowUpStatus(payload.status.upper())
    except ValueError as exc:
        raise ValidationError(f"Invalid follow-up status '{payload.status}'.") from exc
    task = FollowUpService(session).set_status(task_id, status_enum)
    session.commit()
    return FollowUpTaskResponse.model_validate(task)


# ---- Analytics ------------------------------------------------------------- #
@router.get("/crm/analytics", response_model=CRMAnalyticsResponse,
            summary="Real CRM analytics (INSUFFICIENT_DATA / NOT_AVAILABLE when applicable)")
def crm_analytics(session: Session = Depends(get_session), role=Depends(_viewer)) -> CRMAnalyticsResponse:
    return CRMAnalyticsResponse.model_validate(compute_crm_analytics(session).as_dict())


def _parse_stage(value: str) -> SalesStage:
    try:
        return SalesStage(value.upper())
    except (ValueError, AttributeError) as exc:
        raise ValidationError(
            f"Invalid stage '{value}'. Expected one of {[s.value for s in SalesStage]}."
        ) from exc
