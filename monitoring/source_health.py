"""Source-health monitoring (§19, §20).

Watches REAL source connectivity transitions recorded on ``SourceHealth`` (by
the existing ``collectors.connectivity`` probe) and emits ``SourceHealthEvent``
rows plus operational Findings. A failure/recovery is emitted once per real
transition (deduped, §20), never on every refresh. Source-health events NEVER
produce business leads (§19) — only operational alerts.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from database.models import (
    AlertSeverity,
    AlertType,
    SourceConnectionStatus,
    SourceHealth,
    SourceHealthEvent,
    SourceHealthEventType,
)
from monitoring.findings import Finding

# Connection statuses that represent a real failure.
_FAILURE_STATUSES = {
    SourceConnectionStatus.AUTHENTICATION_FAILED.value,
    SourceConnectionStatus.RATE_LIMITED.value,
    SourceConnectionStatus.TEMPORARILY_UNAVAILABLE.value,
    SourceConnectionStatus.ERROR.value,
}
_OK_STATUS = SourceConnectionStatus.CONNECTED.value

# Map a (new) connection status to a health-event type.
_STATUS_TO_EVENT: dict[str, SourceHealthEventType] = {
    SourceConnectionStatus.AUTHENTICATION_FAILED.value: SourceHealthEventType.SOURCE_AUTH_FAILED,
    SourceConnectionStatus.RATE_LIMITED.value: SourceHealthEventType.SOURCE_RATE_LIMITED,
    SourceConnectionStatus.TEMPORARILY_UNAVAILABLE.value: SourceHealthEventType.SOURCE_FAILED,
    SourceConnectionStatus.ERROR.value: SourceHealthEventType.SOURCE_FAILED,
    SourceConnectionStatus.CONNECTED.value: SourceHealthEventType.SOURCE_CONNECTED,
}


@dataclass
class SourceHealthSummary:
    events: list[SourceHealthEvent] = field(default_factory=list)
    findings: list[Finding] = field(default_factory=list)


def _status_value(status) -> str:
    return status.value if hasattr(status, "value") else str(status)


def _latest_event_status(session: Session, source_id: str) -> str | None:
    """The ``new_status`` of the most recent recorded health event for a source —
    our notion of the 'previous' status for transition detection."""
    row = session.execute(
        select(SourceHealthEvent)
        .where(SourceHealthEvent.source_id == source_id)
        .order_by(SourceHealthEvent.detected_at.desc(), SourceHealthEvent.id.desc())
        .limit(1)
    ).scalars().first()
    return row.new_status if row else None


def evaluate_transition(
    source_id: str, previous_status: str | None, new_status: str, *,
    last_failure_at: datetime | None, last_success_at: datetime | None,
    now: datetime, message: str | None = None,
) -> tuple[SourceHealthEvent | None, Finding | None]:
    """Pure transition evaluation. Returns (event, finding) or (None, None) when
    there is no meaningful, non-duplicate transition."""
    if new_status == previous_status:
        return None, None   # no transition → no duplicate event (§20)

    is_failure = new_status in _FAILURE_STATUSES
    was_failure = previous_status in _FAILURE_STATUSES if previous_status else False
    recovered = new_status == _OK_STATUS and was_failure

    if recovered:
        event_type = SourceHealthEventType.SOURCE_RECOVERED
        stamp = (last_success_at or now).isoformat()
    elif is_failure:
        event_type = _STATUS_TO_EVENT.get(new_status, SourceHealthEventType.SOURCE_FAILED)
        stamp = (last_failure_at or now).isoformat()
    elif new_status == _OK_STATUS:
        event_type = SourceHealthEventType.SOURCE_CONNECTED
        stamp = (last_success_at or now).isoformat()
    else:
        # Transitions to NOT_CONFIGURED/CONFIGURED/DISABLED are not events.
        return None, None

    event = SourceHealthEvent(
        source_id=source_id,
        event_type=event_type,
        previous_status=previous_status,
        new_status=new_status,
        message=(message or "")[:512] or None,
        detected_at=now,
        dedup_key=f"src:{source_id}:{event_type.value}:{stamp}",
    )

    finding: Finding | None = None
    if event_type in (
        SourceHealthEventType.SOURCE_FAILED,
        SourceHealthEventType.SOURCE_AUTH_FAILED,
        SourceHealthEventType.SOURCE_RATE_LIMITED,
    ):
        severity = (AlertSeverity.HIGH if event_type is SourceHealthEventType.SOURCE_AUTH_FAILED
                    else AlertSeverity.MEDIUM)
        finding = Finding(
            alert_type=AlertType.SOURCE_FAILURE,
            severity=severity,
            title=f"Source {source_id}: {event_type.value.replace('SOURCE_', '').lower()}",
            message=message or f"{source_id} transitioned {previous_status} → {new_status}.",
            dedup_key=event.dedup_key,
            source_id=source_id,
            link="/monitoring",
            provenance="OPERATIONAL",
        )
    elif event_type is SourceHealthEventType.SOURCE_RECOVERED:
        finding = Finding(
            alert_type=AlertType.SOURCE_RECOVERED,
            severity=AlertSeverity.LOW,
            title=f"Source {source_id} recovered",
            message=message or f"{source_id} recovered ({previous_status} → {new_status}).",
            dedup_key=event.dedup_key,
            source_id=source_id,
            link="/monitoring",
            provenance="OPERATIONAL",
        )
    return event, finding


def scan_source_health(session: Session, *, now: datetime, scheduler_run_id: int | None = None) -> SourceHealthSummary:
    """Compare each source's current ``SourceHealth`` status against its last
    recorded event status and persist any real transitions (idempotently)."""
    summary = SourceHealthSummary()
    rows = session.execute(select(SourceHealth)).scalars().all()
    for health in rows:
        new_status = _status_value(health.connection_status)
        previous = _latest_event_status(session, health.source_id)
        event, finding = evaluate_transition(
            health.source_id, previous, new_status,
            last_failure_at=health.last_failure_at, last_success_at=health.last_success_at,
            now=now, message=health.last_error,
        )
        if event is None:
            continue
        # Idempotency: skip if this exact transition was already recorded.
        exists = session.execute(
            select(SourceHealthEvent.id).where(SourceHealthEvent.dedup_key == event.dedup_key)
        ).scalars().first()
        if exists:
            continue
        event.scheduler_run_id = scheduler_run_id
        session.add(event)
        summary.events.append(event)
        if finding is not None:
            summary.findings.append(finding)
    if summary.events:
        session.flush()
    return summary
