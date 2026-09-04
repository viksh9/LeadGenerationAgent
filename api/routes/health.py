"""Health check route."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from api.schemas import HealthResponse
from config import Settings
from api.dependencies import get_app_settings

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
