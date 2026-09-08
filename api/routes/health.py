"""Health check routes: liveness (/health) and readiness (/health/ready)."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.orm import Session

from api.schemas import HealthResponse, ReadinessResponse
from config import Settings
from api.dependencies import get_app_settings, get_session

logger = logging.getLogger(__name__)
router = APIRouter(tags=["health"])


@router.get(
    "/health",
    response_model=HealthResponse,
    summary="Health check",
    description="Liveness probe. Returns application status, name, environment, and version.",
)
def health(settings: Settings = Depends(get_app_settings)) -> HealthResponse:
    return HealthResponse(
        status="healthy",
        app=settings.app_name,
        environment=settings.environment,
        version=settings.version,
    )


@router.get(
    "/health/live",
    response_model=HealthResponse,
    summary="Liveness probe",
    description="Process is alive. No dependency checks — used by orchestrators to "
                "decide whether to restart the container.",
)
def liveness(settings: Settings = Depends(get_app_settings)) -> HealthResponse:
    return HealthResponse(
        status="alive",
        app=settings.app_name,
        environment=settings.environment,
        version=settings.version,
    )


@router.get(
    "/health/ready",
    response_model=ReadinessResponse,
    summary="Readiness check",
    description=(
        "Verifies the application and its required infrastructure (database). "
        "Optional external providers (email/CRM/AI/sources) are reported for "
        "visibility but do NOT make the app unready — a missing optional provider "
        "is a valid, healthy state (§52)."
    ),
)
def readiness(
    settings: Settings = Depends(get_app_settings),
    session: Session = Depends(get_session),
) -> ReadinessResponse:
    checks: dict = {}
    ready = True
    # Required: database connectivity.
    try:
        session.execute(text("SELECT 1"))
        checks["database"] = "ok"
    except Exception as exc:  # noqa: BLE001
        checks["database"] = "error"
        ready = False
        logger.warning("readiness: database check failed: %s", type(exc).__name__)

    # Informational only (never flips readiness).
    checks["data_mode"] = settings.data_mode
    checks["scheduler"] = "enabled" if settings.scheduler_active else "disabled"
    checks["ai_provider"] = settings.ai_config_status
    checks["email_provider"] = settings.email_config_status
    checks["crm_provider"] = settings.crm_config_status

    return ReadinessResponse(status="ready" if ready else "not_ready", checks=checks)
