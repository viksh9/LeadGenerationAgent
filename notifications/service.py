"""NotificationService — the single writer of ``Alert`` rows (§26–§33).

Applies, in order: provenance gating (business alerts require REAL), user
preferences (enabled types, min severity, hot-leads-only), and deduplication
(``deduplication_key`` uniqueness). Alerts are only ever created from real
monitoring Findings; this service never derives facts of its own.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from database.models import (
    Alert,
    AlertSeverity,
    AlertStatus,
    AlertType,
    DataProvenance,
    NotificationPreference,
)
from database.models import utcnow
from monitoring.findings import Finding
from notifications.preferences import get_or_create_preferences

# Alert types that are OPERATIONAL (source health) rather than business (§19, §33).
_OPERATIONAL_TYPES = {AlertType.SOURCE_FAILURE, AlertType.SOURCE_RECOVERED}

_SEVERITY_RANK = {
    AlertSeverity.LOW: 0, AlertSeverity.MEDIUM: 1, AlertSeverity.HIGH: 2, AlertSeverity.CRITICAL: 3,
}

# Preference filter: with hot_leads_only, low-signal score bumps are suppressed.
_HOT_ONLY_SUPPRESSED = {AlertType.LEAD_SCORE_INCREASED}


@dataclass
class EmitResult:
    created: list[Alert] = field(default_factory=list)
    skipped_duplicate: int = 0
    skipped_preference: int = 0
    skipped_provenance: int = 0

    @property
    def created_count(self) -> int:
        return len(self.created)


class NotificationService:
    def __init__(self, session: Session):
        self.session = session

    # ------------------------------------------------------------------ #
    # Emit
    # ------------------------------------------------------------------ #
    def emit(self, findings: list[Finding], *, now: datetime | None = None,
             preferences: NotificationPreference | None = None) -> EmitResult:
        now = now or utcnow()
        prefs = preferences or get_or_create_preferences(self.session)
        enabled = set(prefs.enabled_alert_types or [])
        min_rank = _SEVERITY_RANK.get(_as_severity(prefs.min_severity), 0)
        result = EmitResult()

        for finding in findings:
            is_operational = finding.alert_type in _OPERATIONAL_TYPES
            # Provenance gate: business alerts must come from REAL data (§33).
            if not is_operational and finding.provenance != "REAL":
                result.skipped_provenance += 1
                continue
            # Preference: enabled types.
            if enabled and finding.alert_type.value not in enabled:
                result.skipped_preference += 1
                continue
            # Preference: minimum severity.
            if _SEVERITY_RANK.get(finding.severity, 0) < min_rank:
                result.skipped_preference += 1
                continue
            # Preference: hot-leads-only suppresses low-signal lead score bumps.
            if prefs.hot_leads_only and finding.alert_type in _HOT_ONLY_SUPPRESSED:
                result.skipped_preference += 1
                continue
            # Deduplication (§28): same condition => same key => no repeat.
            if self._exists(finding.dedup_key):
                result.skipped_duplicate += 1
                continue
            alert = self._build_alert(finding, now)
            self.session.add(alert)
            result.created.append(alert)

        if result.created:
            self.session.flush()
        return result

    def _exists(self, dedup_key: str) -> bool:
        return self.session.execute(
            select(Alert.id).where(Alert.deduplication_key == dedup_key)
        ).scalars().first() is not None

    def _build_alert(self, f: Finding, now: datetime) -> Alert:
        return Alert(
            alert_type=f.alert_type,
            severity=f.severity,
            company_id=f.company_id,
            lead_id=f.lead_id,
            opportunity_id=f.opportunity_id,
            signal_id=f.signal_id,
            tender_id=f.tender_id,
            source_id=f.source_id,
            title=f.title[:255],
            message=f.message,
            evidence_ids=list(f.evidence_ids or []),
            link=f.link,
            status=AlertStatus.NEW,
            channel="IN_APP",
            deduplication_key=f.dedup_key[:200],
            data_provenance=DataProvenance.REAL,
            triggered_at=now,
        )

    # ------------------------------------------------------------------ #
    # Query / lifecycle
    # ------------------------------------------------------------------ #
    def list_alerts(self, *, status: AlertStatus | None = None, limit: int = 50,
                    offset: int = 0) -> list[Alert]:
        stmt = select(Alert)
        if status is not None:
            stmt = stmt.where(Alert.status == status)
        stmt = stmt.order_by(Alert.triggered_at.desc(), Alert.id.desc()).limit(limit).offset(offset)
        return list(self.session.execute(stmt).scalars().all())

    def unread_count(self) -> int:
        return int(self.session.execute(
            select(func.count(Alert.id)).where(Alert.status == AlertStatus.NEW)
        ).scalar() or 0)

    def get(self, alert_id: int) -> Alert | None:
        return self.session.get(Alert, alert_id)

    def set_status(self, alert_id: int, status: AlertStatus, *, now: datetime | None = None) -> Alert | None:
        now = now or utcnow()
        alert = self.get(alert_id)
        if alert is None:
            return None
        alert.status = status
        if status is AlertStatus.ACKNOWLEDGED:
            alert.acknowledged_at = now
        elif status is AlertStatus.RESOLVED:
            alert.resolved_at = now
        alert.updated_at = now
        self.session.flush()
        return alert


def _as_severity(value) -> AlertSeverity:
    if isinstance(value, AlertSeverity):
        return value
    try:
        return AlertSeverity(value)
    except Exception:
        return AlertSeverity.LOW
