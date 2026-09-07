"""Real-data source connectivity status endpoint.

Exposes a truthful view of every catalogued source: whether its collector is
implemented, whether it is configured, and whether it is actually connected.
Never reports CONNECTED from configuration alone — only a real, verified live
health check can set that. No network calls are made to serve this endpoint.
"""

from __future__ import annotations

from fastapi import APIRouter

from api.schemas import SourceStatusListResponse, SourceStatusResponse
from collectors.source_status import RuntimeSourceStatus, all_source_status

router = APIRouter(prefix="/sources", tags=["sources"])


@router.get(
    "",
    response_model=SourceStatusListResponse,
    summary="Real-data source status",
    description=(
        "Truthful connectivity status for every catalogued real-data source. "
        "A source is CONNECTED only after a verified live health check; a "
        "configured or implemented collector is not the same as an active "
        "real-data connection."
    ),
)
def list_sources_endpoint() -> SourceStatusListResponse:
    reports = all_source_status()
    items = [SourceStatusResponse.model_validate(r) for r in reports]
    connected = sum(1 for r in reports if r.status is RuntimeSourceStatus.CONNECTED)
    configured = sum(1 for r in reports if r.status is RuntimeSourceStatus.CONFIGURED)
    return SourceStatusListResponse(
        items=items,
        total=len(items),
        connected_count=connected,
        configured_count=configured,
        any_connected=connected > 0,
    )
