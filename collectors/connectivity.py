"""Source connectivity service — the ONLY path that can mark a source CONNECTED.

``check_source_connection`` performs a real, credential-based request (via the
collector's ``health_check``), classifies the outcome, and persists it to the
``source_health`` table (last_checked/success/failure, error, counters). It makes
network calls, so it is invoked only on demand (CLI / explicit API), never at
startup or in the default test suite.

Truthfulness:
  * CONNECTED is set only when a real request actually succeeds.
  * Credentials are never logged or persisted; ``last_error`` is a safe message.
  * Unconfigured or not-yet-implemented sources are reported honestly without a
    network call.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from collectors.base import HealthStatus
from collectors.errors import CollectorError
from collectors.registry import build_collector, is_runnable
from collectors.source_registry import SourceStatus, get_registry
from database.models import SourceConnectionStatus, SourceHealth

logger = logging.getLogger("collectors.connectivity")

# collector HealthStatus -> persisted connection status
_HEALTH_TO_STATUS: dict[HealthStatus, SourceConnectionStatus] = {
    HealthStatus.HEALTHY: SourceConnectionStatus.CONNECTED,
    HealthStatus.DEGRADED: SourceConnectionStatus.CONNECTED,
    HealthStatus.NOT_CONFIGURED: SourceConnectionStatus.NOT_CONFIGURED,
    HealthStatus.AUTHENTICATION_FAILED: SourceConnectionStatus.AUTHENTICATION_FAILED,
    HealthStatus.RATE_LIMITED: SourceConnectionStatus.RATE_LIMITED,
    HealthStatus.UNAVAILABLE: SourceConnectionStatus.TEMPORARILY_UNAVAILABLE,
    HealthStatus.RESTRICTED: SourceConnectionStatus.ERROR,
}


@dataclass
class ConnectionCheckResult:
    source_id: str
    status: SourceConnectionStatus
    message: Optional[str]
    checked_at: datetime
    performed_request: bool  # False when we reported config state without a network call


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def get_source_health(session: Session, source_id: str) -> Optional[SourceHealth]:
    return session.scalar(select(SourceHealth).where(SourceHealth.source_id == source_id))


def _upsert_health(session: Session, source_id: str) -> SourceHealth:
    health = get_source_health(session, source_id)
    if health is None:
        health = SourceHealth(source_id=source_id)
        session.add(health)
    return health


def _record(session: Session, source_id: str, status: SourceConnectionStatus,
            message: Optional[str], *, performed_request: bool) -> SourceHealth:
    now = _now()
    health = _upsert_health(session, source_id)
    health.connection_status = status
    if performed_request:
        health.last_checked_at = now
        health.checks_total = (health.checks_total or 0) + 1
        if status is SourceConnectionStatus.CONNECTED:
            health.last_success_at = now
            health.checks_ok = (health.checks_ok or 0) + 1
            health.last_error = None
        else:
            health.last_failure_at = now
            health.last_error = (message or status.value)[:512]
    session.commit()
    return health


def check_source_connection(session: Session, source_id: str) -> ConnectionCheckResult:
    """Run a real connectivity check for one source and persist the outcome.

    For sources without a runnable collector, reports the honest configuration
    state (NOT_CONFIGURED / DISABLED / ERROR) WITHOUT a network request.
    """
    source = get_registry().get(source_id)
    if source is None:
        raise CollectorError(f"Unknown source '{source_id}'.")

    if source.status is SourceStatus.DISABLED:
        result = _record(session, source_id, SourceConnectionStatus.DISABLED,
                         "Source is disabled.", performed_request=False)
        return ConnectionCheckResult(source_id, result.connection_status, result.last_error, _now(), False)

    if not is_runnable(source_id):
        # No source_id-runnable collector (e.g. career pages need per-source config).
        status = SourceConnectionStatus.NOT_CONFIGURED
        msg = "No runnable collector for this source; configure per-source settings."
        result = _record(session, source_id, status, msg, performed_request=False)
        return ConnectionCheckResult(source_id, result.connection_status, msg, _now(), False)

    collector = build_collector(source_id)
    try:
        health = collector.health_check()   # performs the real request when configured
    except CollectorError as exc:           # defensive: health_check normally classifies
        result = _record(session, source_id, SourceConnectionStatus.ERROR, str(exc), performed_request=True)
        return ConnectionCheckResult(source_id, result.connection_status, str(exc), _now(), True)

    status = _HEALTH_TO_STATUS.get(health.status, SourceConnectionStatus.ERROR)
    performed = health.status is not HealthStatus.NOT_CONFIGURED
    result = _record(session, source_id, status, health.message, performed_request=performed)
    logger.info("source_connectivity source_id=%s status=%s", source_id, status.value)
    return ConnectionCheckResult(source_id, result.connection_status, health.message, _now(), performed)
