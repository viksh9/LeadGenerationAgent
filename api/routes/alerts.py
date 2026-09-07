"""Alert center, notification preferences, and the operational monitoring
dashboard (§25, §26, §31, §32).

All metrics are actual database/operational values — never fabricated. Alerts are
read/acknowledged/dismissed/resolved here; they are only ever created by the
monitoring layer from REAL change events.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from api.dependencies import get_session, require_admin
from api.schemas import (
    AlertListResponse,
    AlertResponse,
    AlertStatusUpdate,
    MonitoringChangeSummary,
    MonitoringDashboardResponse,
    MonitoringPipelineMetrics,
    MonitoringSourceMetric,
    NotificationPreferenceResponse,
    NotificationPreferenceUpdate,
    SchedulerRunResponse,
    ScheduledJobResponse,
)
from config import get_settings
from config.exceptions import NotFoundError, ValidationError
from database.models import (
    Alert,
    AlertStatus,
    BusinessSignal,
    Company,
    JobChangeEvent,
    JobRecord,
    Lead,
    OpportunityCandidate,
    RawSourceRecord,
    SchedulerRun,
    SourceHealth,
    TenderRecord,
    utcnow,
)
from notifications.preferences import get_or_create_preferences, update_preferences
from notifications.service import NotificationService
from scheduler.service import SchedulerService

logger = logging.getLogger(__name__)
router = APIRouter(tags=["alerts"])


# --------------------------------------------------------------------------- #
# Alert center
# --------------------------------------------------------------------------- #
@router.get("/alerts", response_model=AlertListResponse, summary="List in-app alerts")
def list_alerts(
    status: str | None = Query(default=None, description="Filter by status (NEW/ACKNOWLEDGED/DISMISSED/RESOLVED)"),
    limit: int = Query(default=50, le=200),
    offset: int = 0,
    session: Session = Depends(get_session),
) -> AlertListResponse:
    svc = NotificationService(session)
    status_enum = _parse_status(status) if status else None
    alerts = svc.list_alerts(status=status_enum, limit=limit, offset=offset)
    total = int(session.execute(select(func.count(Alert.id))).scalar() or 0)
    return AlertListResponse(
        items=[AlertResponse.model_validate(a) for a in alerts],
        total=total,
        unread_count=svc.unread_count(),
    )


@router.get("/alerts/unread-count", summary="Unread alert count")
def unread_count(session: Session = Depends(get_session)) -> dict:
    return {"unread_count": NotificationService(session).unread_count()}


@router.get("/alerts/{alert_id}", response_model=AlertResponse, summary="Get one alert")
def get_alert(alert_id: int, session: Session = Depends(get_session)) -> AlertResponse:
    alert = NotificationService(session).get(alert_id)
    if alert is None:
        raise NotFoundError(f"Alert {alert_id} not found.")
    return AlertResponse.model_validate(alert)


@router.post("/alerts/{alert_id}/status", response_model=AlertResponse,
             summary="Update alert status (acknowledge/dismiss/resolve)")
def set_alert_status(alert_id: int, payload: AlertStatusUpdate,
                     session: Session = Depends(get_session)) -> AlertResponse:
    status_enum = _parse_status(payload.status)
    alert = NotificationService(session).set_status(alert_id, status_enum)
    if alert is None:
        raise NotFoundError(f"Alert {alert_id} not found.")
    session.commit()
    return AlertResponse.model_validate(alert)


def _parse_status(value: str) -> AlertStatus:
    try:
        return AlertStatus(value.upper())
    except Exception as exc:
        raise ValidationError(
            f"Invalid alert status '{value}'. Expected one of "
            f"{[s.value for s in AlertStatus]}."
        ) from exc


# --------------------------------------------------------------------------- #
# Notification preferences
# --------------------------------------------------------------------------- #
@router.get("/notification-preferences", response_model=NotificationPreferenceResponse,
            summary="Get alert preferences")
def get_preferences(session: Session = Depends(get_session)) -> NotificationPreferenceResponse:
    pref = get_or_create_preferences(session)
    session.commit()
    return NotificationPreferenceResponse.model_validate(pref)


@router.put("/notification-preferences", response_model=NotificationPreferenceResponse,
            summary="Update alert preferences")
def put_preferences(payload: NotificationPreferenceUpdate,
                    session: Session = Depends(get_session)) -> NotificationPreferenceResponse:
    pref = update_preferences(session, **payload.model_dump(exclude_none=True))
    session.commit()
    return NotificationPreferenceResponse.model_validate(pref)


# --------------------------------------------------------------------------- #
# Monitoring dashboard (§25)
# --------------------------------------------------------------------------- #
@router.get("/monitoring/dashboard", response_model=MonitoringDashboardResponse,
            summary="Operational monitoring dashboard (real metrics)")
def monitoring_dashboard(session: Session = Depends(get_session)) -> MonitoringDashboardResponse:
    settings = get_settings()

    pipeline = MonitoringPipelineMetrics(
        raw_records=_count(session, RawSourceRecord),
        canonical_jobs=_count(session, JobRecord),
        companies=_count(session, Company),
        signals=_count(session, BusinessSignal),
        opportunities=_count(session, OpportunityCandidate),
        leads=_count(session, Lead),
        tenders=_count(session, TenderRecord),
    )

    # Sources: health + latest run per source.
    sources: list[MonitoringSourceMetric] = []
    health_rows = session.execute(select(SourceHealth)).scalars().all()
    for h in health_rows:
        latest_run = session.execute(
            select(SchedulerRun).where(SchedulerRun.source_id == h.source_id)
            .order_by(SchedulerRun.started_at.desc()).limit(1)
        ).scalars().first()
        sources.append(MonitoringSourceMetric(
            source_id=h.source_id,
            connection_status=(h.connection_status.value if hasattr(h.connection_status, "value")
                               else str(h.connection_status)),
            last_success_at=h.last_success_at,
            last_failure_at=h.last_failure_at,
            last_error=h.last_error,
            last_run_at=(latest_run.started_at if latest_run else None),
            records_fetched=(latest_run.records_fetched if latest_run else 0),
        ))

    svc = SchedulerService(session)
    jobs = svc.list_jobs()
    recent_runs = session.execute(
        select(SchedulerRun).order_by(SchedulerRun.started_at.desc()).limit(10)
    ).scalars().all()
    recent_alerts = NotificationService(session).list_alerts(limit=10)

    change_rows = session.execute(
        select(JobChangeEvent.change_type, func.count(JobChangeEvent.id))
        .group_by(JobChangeEvent.change_type)
    ).all()
    change_summary = [
        MonitoringChangeSummary(
            change_type=(ct.value if hasattr(ct, "value") else str(ct)), count=int(n)
        )
        for ct, n in change_rows
    ]

    return MonitoringDashboardResponse(
        generated_at=utcnow(),
        scheduler_enabled=settings.scheduler_active,
        data_mode=settings.data_mode,
        pipeline=pipeline,
        sources=sources,
        jobs=[ScheduledJobResponse.model_validate(j) for j in jobs],
        recent_runs=[SchedulerRunResponse.model_validate(r) for r in recent_runs],
        recent_alerts=[AlertResponse.model_validate(a) for a in recent_alerts],
        unread_alerts=NotificationService(session).unread_count(),
        job_change_summary=change_summary,
    )


def _count(session: Session, model) -> int:
    return int(session.execute(select(func.count()).select_from(model)).scalar() or 0)
