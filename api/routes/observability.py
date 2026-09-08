"""Operational metrics endpoint (Prompt 40 §27, §58).

Reports ACTUAL operational counts from the database + in-process runtime state
(circuit breakers). These are operational metrics, kept separate from market
intelligence. Nothing here is fabricated; empty deployments report zeros.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from api.dependencies import get_session
from config import get_settings
from database.models import (
    Alert,
    CollectionRun,
    CollectionRunStatus,
    CRMActivity,
    CRMSyncRecord,
    DataProvenance,
    JobRecord,
    Lead,
    OpportunityCandidate,
    OutreachDraft,
    OutreachDraftStatus,
    RawSourceRecord,
    SchedulerRun,
    SchedulerRunStatus,
    SourceHealth,
    SyncConflict,
    utcnow,
)
from database.models import BusinessSignal

router = APIRouter(tags=["observability"])


def _count(session: Session, model, *where) -> int:
    stmt = select(func.count()).select_from(model)
    for w in where:
        stmt = stmt.where(w)
    return int(session.execute(stmt).scalar() or 0)


@router.get("/monitoring/metrics", summary="Operational metrics (real counts)")
def operational_metrics(session: Session = Depends(get_session)) -> dict:
    settings = get_settings()

    # Sources.
    source_health = session.execute(select(SourceHealth)).scalars().all()
    sources = {
        "configured": sum(1 for s in source_health),
        "connected": sum(1 for s in source_health
                         if getattr(s.connection_status, "value", s.connection_status) == "CONNECTED"),
        "by_status": {},
    }
    for s in source_health:
        st = getattr(s.connection_status, "value", str(s.connection_status))
        sources["by_status"][st] = sources["by_status"].get(st, 0) + 1

    # Ingestion (collection runs).
    ingestion = {
        "runs": _count(session, CollectionRun),
        "failed_runs": _count(session, CollectionRun, CollectionRun.status == CollectionRunStatus.FAILED),
        "raw_records": _count(session, RawSourceRecord),
        "canonical_jobs": _count(session, JobRecord),
    }

    # Processing / intelligence.
    processing = {
        "signals": _count(session, BusinessSignal),
        "opportunities": _count(session, OpportunityCandidate),
        "leads": _count(session, Lead, Lead.data_provenance == DataProvenance.REAL),
    }

    # Outreach.
    outreach = {
        "drafts": _count(session, OutreachDraft),
        "sent": _count(session, OutreachDraft, OutreachDraft.status == OutreachDraftStatus.SENT),
        "failed": _count(session, OutreachDraft, OutreachDraft.status == OutreachDraftStatus.FAILED),
    }

    # Scheduler.
    scheduler = {
        "runs": _count(session, SchedulerRun),
        "failed": _count(session, SchedulerRun, SchedulerRun.status == SchedulerRunStatus.FAILED),
    }

    # CRM.
    crm = {
        "activities": _count(session, CRMActivity),
        "sync_records": _count(session, CRMSyncRecord),
        "sync_conflicts": _count(session, SyncConflict, SyncConflict.resolved.is_(False)),
    }

    # Alerts (operational + business alerts count).
    alerts = {"total": _count(session, Alert)}

    # Runtime resilience state.
    from resilience.circuit_breaker import all_breaker_states
    circuit_breakers = all_breaker_states()

    return {
        "generated_at": utcnow().isoformat(),
        "environment": settings.environment,
        "data_mode": settings.data_mode,
        "sources": sources,
        "ingestion": ingestion,
        "processing": processing,
        "outreach": outreach,
        "scheduler": scheduler,
        "crm": crm,
        "alerts": alerts,
        "circuit_breakers": circuit_breakers,
        "providers": {
            "ai": settings.ai_config_status,
            "email": settings.email_config_status,
            "crm": settings.crm_config_status,
        },
    }
