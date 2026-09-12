"""Real-data source connectivity status + on-demand connectivity checks.

Exposes a truthful view of every catalogued source: configuration readiness
(``status``), declared capabilities, licensing, and the outcome of the last real
connectivity check (``connection_status`` + timestamps, from the source_health
table). A source is CONNECTED only after a verified live request — never from
configuration alone. Credentials are never exposed.

GET endpoints make no network calls. The POST check endpoint performs a real,
credential-based request on demand.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from api.dependencies import get_session
from api.schemas import (
    SourceCheckResponse,
    SourceStatusListResponse,
    SourceStatusResponse,
)
from sqlalchemy import select

from collectors.connectivity import check_source_connection, get_source_health
from collectors.source_status import all_source_status
from config.exceptions import NotFoundError
from config.settings import get_settings
from database.models import (
    AtsProvider,
    CollectionRun,
    CollectionRunStatus,
    CompanyCareerSource,
    SourceConnectionStatus,
    SourceHealth,
)

router = APIRouter(prefix="/sources", tags=["sources"])

# ATS sources are configured via DB-registered boards (CompanyCareerSource), not env.
_ATS_SOURCE_PROVIDER = {"greenhouse": AtsProvider.GREENHOUSE, "lever": AtsProvider.LEVER}


def _apply_ats_boards(item: SourceStatusResponse, boards: list[CompanyCareerSource]) -> None:
    """Reflect wired ATS boards on a source row so the dashboard shows CONFIGURED/CONNECTED
    (and how many boards) instead of the env-only DISCOVERY_REQUIRED. Connection is only
    CONNECTED when a board actually had a real success."""
    if not boards:
        return
    item.status = "CONFIGURED"
    item.detail = f"{len(boards)} board(s) wired: {', '.join(b.board_identifier for b in boards[:5])}"
    successes = [b.last_success_at for b in boards if b.last_success_at]
    if successes and item.connection_status != SourceConnectionStatus.CONNECTED.value:
        item.connection_status = SourceConnectionStatus.CONNECTED.value
        item.last_success_at = item.last_success_at or max(successes)


def _merge(report, health: SourceHealth | None, run: CollectionRun | None) -> SourceStatusResponse:
    resp = SourceStatusResponse(
        source_id=report.source_id,
        name=report.name,
        category=report.category,
        source_type=report.source_type,
        provider=report.provider,
        collector_implemented=report.collector_implemented,
        requires_api_key=report.requires_api_key,
        authentication_type=report.authentication_type,
        credential_env_vars=report.credential_env_vars,
        capabilities=report.capabilities,
        supports_india=report.supports_india,
        reliability_tier=report.reliability_tier,
        status=report.status.value,
        detail=report.detail,
        priority=report.priority,
        commercial_use_status=report.commercial_use_status,
        documentation_url=report.documentation_url,
        terms_url=report.terms_url,
    )
    if health is not None:
        resp.connection_status = health.connection_status.value
        resp.last_checked_at = health.last_checked_at
        resp.last_success_at = health.last_success_at
        resp.last_failure_at = health.last_failure_at
        resp.last_error = health.last_error
    if run is not None:
        resp.last_ingestion_at = run.completed_at or run.started_at
        resp.last_ingestion_records_fetched = run.records_fetched
        resp.last_ingestion_records_persisted = run.records_created
    return resp


def _latest_runs(session: Session) -> dict[str, CollectionRun]:
    """Most recent COMPLETED collection run per source_id."""
    runs = session.execute(
        select(CollectionRun)
        .where(CollectionRun.status == CollectionRunStatus.COMPLETED)
        .order_by(CollectionRun.started_at.desc())
    ).scalars().all()
    latest: dict[str, CollectionRun] = {}
    for run in runs:
        latest.setdefault(run.source_id, run)
    return latest


def _list(session: Session) -> SourceStatusListResponse:
    reports = all_source_status()
    health_by_id = {h.source_id: h for h in session.query(SourceHealth).all()}
    runs_by_id = _latest_runs(session)
    items = [_merge(r, health_by_id.get(r.source_id), runs_by_id.get(r.source_id)) for r in reports]

    # Reflect DB-registered ATS boards (Greenhouse/Lever) so the dashboard's Real Data
    # Sources panel updates as boards are wired — not tied to the (empty) env vars.
    ats_boards: dict[AtsProvider, list[CompanyCareerSource]] = {}
    for cs in session.query(CompanyCareerSource).filter(CompanyCareerSource.enabled.is_(True)).all():
        if cs.board_identifier:
            ats_boards.setdefault(cs.ats_provider, []).append(cs)
    for item in items:
        _apply_ats_boards(item, ats_boards.get(_ATS_SOURCE_PROVIDER.get(item.source_id), []))
    # CONNECTED is only true from a persisted, verified check.
    connected = sum(1 for it in items if it.connection_status == SourceConnectionStatus.CONNECTED.value)
    configured = sum(1 for it in items if it.status == "CONFIGURED")
    return SourceStatusListResponse(
        data_mode=get_settings().data_mode,
        items=items,
        total=len(items),
        connected_count=connected,
        configured_count=configured,
        any_connected=connected > 0,
    )


@router.get(
    "",
    response_model=SourceStatusListResponse,
    summary="Real-data source status",
    description=(
        "Truthful status for every catalogued real-data source: configuration "
        "readiness, capabilities, licensing, and the last verified connectivity "
        "check. CONNECTED only ever appears after a real request succeeded."
    ),
)
def list_sources_endpoint(session: Session = Depends(get_session)) -> SourceStatusListResponse:
    return _list(session)


@router.get(
    "/status",
    response_model=SourceStatusListResponse,
    summary="Real-data source status (alias)",
    description="Alias of GET /sources — same truthful source status payload.",
)
def sources_status_endpoint(session: Session = Depends(get_session)) -> SourceStatusListResponse:
    return _list(session)


@router.post(
    "/{source_id}/check",
    response_model=SourceCheckResponse,
    summary="Check a source connection (real request)",
    description=(
        "Perform a real, credential-based connectivity check for one source and "
        "persist the outcome. Sources without credentials report NOT_CONFIGURED "
        "and make no network call. A source becomes CONNECTED only if the request "
        "actually succeeds."
    ),
)
def check_source_endpoint(
    source_id: str, session: Session = Depends(get_session)
) -> SourceCheckResponse:
    from collectors.errors import CollectorError

    try:
        result = check_source_connection(session, source_id)
    except CollectorError as exc:
        raise NotFoundError(str(exc))
    return SourceCheckResponse(
        source_id=result.source_id,
        connection_status=result.status.value,
        message=result.message,
        performed_request=result.performed_request,
        checked_at=result.checked_at,
    )
