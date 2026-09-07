"""Scheduler control endpoints (§39).

Read endpoints are open (single-user app); mutating/operational actions (run,
pause, resume) require the admin guard (§44). No endpoint executes arbitrary
code, fetches arbitrary URLs, or exposes credentials — jobs run only registered,
source-config-bound collectors and deterministic monitoring handlers.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from api.dependencies import get_session, require_admin
from api.schemas import (
    ScheduledJobListResponse,
    ScheduledJobResponse,
    SchedulerRunListResponse,
    SchedulerRunResponse,
)
from config import get_settings
from config.exceptions import NotFoundError
from database.models import SchedulerRun
from scheduler.service import SchedulerService

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/scheduler", tags=["scheduler"])


@router.get("/jobs", response_model=ScheduledJobListResponse, summary="List scheduled jobs")
def list_jobs(session: Session = Depends(get_session)) -> ScheduledJobListResponse:
    svc = SchedulerService(session)
    jobs = svc.list_jobs()
    if not jobs:
        # Seed the default job set on first read so the operator sees the plan.
        svc.seed_default_jobs()
        session.commit()
        jobs = svc.list_jobs()
    return ScheduledJobListResponse(
        items=[ScheduledJobResponse.model_validate(j) for j in jobs],
        total=len(jobs),
        scheduler_enabled=get_settings().scheduler_active,
    )


@router.get("/jobs/{job_id}", response_model=ScheduledJobResponse, summary="Get one scheduled job")
def get_job(job_id: int, session: Session = Depends(get_session)) -> ScheduledJobResponse:
    job = SchedulerService(session).get(job_id)
    if job is None:
        raise NotFoundError(f"Scheduled job {job_id} not found.")
    return ScheduledJobResponse.model_validate(job)


@router.get("/jobs/{job_id}/runs", response_model=SchedulerRunListResponse,
            summary="Recent runs for a job")
def job_runs(job_id: int, limit: int = 20, session: Session = Depends(get_session)) -> SchedulerRunListResponse:
    job = SchedulerService(session).get(job_id)
    if job is None:
        raise NotFoundError(f"Scheduled job {job_id} not found.")
    rows = session.execute(
        select(SchedulerRun).where(SchedulerRun.job_id == job_id)
        .order_by(SchedulerRun.started_at.desc()).limit(limit)
    ).scalars().all()
    return SchedulerRunListResponse(
        items=[SchedulerRunResponse.model_validate(r) for r in rows], total=len(rows),
    )


@router.get("/runs", response_model=SchedulerRunListResponse, summary="Recent scheduler runs")
def recent_runs(limit: int = 50, session: Session = Depends(get_session)) -> SchedulerRunListResponse:
    rows = session.execute(
        select(SchedulerRun).order_by(SchedulerRun.started_at.desc()).limit(limit)
    ).scalars().all()
    return SchedulerRunListResponse(
        items=[SchedulerRunResponse.model_validate(r) for r in rows], total=len(rows),
    )


@router.post("/jobs/{job_id}/run", response_model=SchedulerRunResponse,
             summary="Manually trigger a job (admin)", dependencies=[Depends(require_admin)])
def run_job(job_id: int, session: Session = Depends(get_session)) -> SchedulerRunResponse:
    svc = SchedulerService(session)
    job = svc.get(job_id)
    if job is None:
        raise NotFoundError(f"Scheduled job {job_id} not found.")
    run = svc.run_job(job, trigger="MANUAL")
    session.commit()
    return SchedulerRunResponse.model_validate(run)


@router.post("/jobs/{job_id}/pause", response_model=ScheduledJobResponse,
             summary="Pause a job (admin)", dependencies=[Depends(require_admin)])
def pause_job(job_id: int, session: Session = Depends(get_session)) -> ScheduledJobResponse:
    job = SchedulerService(session).pause(job_id)
    if job is None:
        raise NotFoundError(f"Scheduled job {job_id} not found.")
    session.commit()
    return ScheduledJobResponse.model_validate(job)


@router.post("/jobs/{job_id}/resume", response_model=ScheduledJobResponse,
             summary="Resume a job (admin)", dependencies=[Depends(require_admin)])
def resume_job(job_id: int, session: Session = Depends(get_session)) -> ScheduledJobResponse:
    job = SchedulerService(session).resume(job_id)
    if job is None:
        raise NotFoundError(f"Scheduled job {job_id} not found.")
    session.commit()
    return ScheduledJobResponse.model_validate(job)
