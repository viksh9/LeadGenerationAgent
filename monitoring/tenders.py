"""Tender & project monitoring (§15, §16, §17).

Operates only on REAL ``TenderRecord`` rows already collected/imported by the
pipeline. It NEVER creates a tender (§15) — it observes newly-collected ones and
watches real closing dates. ``CLOSING_SOON`` fires only for a tender that is
still open, has a known closing date, and falls inside the configured window
(§16); expired/cancelled tenders never alert.
"""

from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from database.models import (
    AlertSeverity,
    AlertType,
    DataProvenance,
    TenderRecord,
    TenderStatus,
)
from monitoring.config import DEFAULT_TENDER_MONITOR, TenderMonitorConfig
from monitoring.findings import Finding

_CLOSED_STATUSES = {TenderStatus.CLOSED.value, TenderStatus.CANCELLED.value, TenderStatus.AWARDED.value}


def _status_value(status) -> str:
    return status.value if hasattr(status, "value") else str(status)


def detect_new_tenders(
    session: Session, *, now: datetime, run_since: datetime | None = None,
) -> list[Finding]:
    """New tenders observed since ``run_since`` (§15). A missing ``run_since``
    means "first run" and yields nothing (we don't retro-alert history)."""
    if run_since is None:
        return []
    tenders = session.execute(
        select(TenderRecord).where(
            TenderRecord.data_provenance == DataProvenance.REAL,
            TenderRecord.first_seen_at >= run_since,
        )
    ).scalars().all()
    findings: list[Finding] = []
    for t in tenders:
        org = t.organization_name or "Unknown organization"
        deadline = f", closes {t.closing_date.date().isoformat()}" if t.closing_date else ""
        findings.append(Finding(
            alert_type=AlertType.NEW_TENDER,
            severity=AlertSeverity.HIGH,
            title=f"New tender: {t.title[:120] if t.title else org}",
            message=f"{org}{deadline}. Source: {t.source_id}.",
            dedup_key=f"tender:{t.id}:NEW",
            company_id=t.company_id or t.target_company_id,
            tender_id=t.id,
            signal_id=t.business_signal_id,
            source_id=t.source_id,
            link=f"/tenders",
        ))
    return findings


def detect_closing_soon(
    session: Session, *, now: datetime, config: TenderMonitorConfig = DEFAULT_TENDER_MONITOR,
) -> list[Finding]:
    """Tenders closing within the window (§16). Only still-open tenders with a
    known future closing date inside the threshold qualify."""
    horizon = now + timedelta(days=config.closing_soon_days)
    open_statuses = set(config.open_statuses)
    tenders = session.execute(
        select(TenderRecord).where(
            TenderRecord.data_provenance == DataProvenance.REAL,
            TenderRecord.closing_date.is_not(None),
        )
    ).scalars().all()
    findings: list[Finding] = []
    for t in tenders:
        status = _status_value(t.tender_status)
        if status in _CLOSED_STATUSES or status not in open_statuses:
            continue
        if t.closing_date is None or t.closing_date < now or t.closing_date > horizon:
            continue
        days_left = (t.closing_date - now).days
        # Closing tomorrow → HIGH (§29); more runway → MEDIUM.
        severity = AlertSeverity.HIGH if days_left <= 1 else AlertSeverity.MEDIUM
        org = t.organization_name or "Unknown organization"
        findings.append(Finding(
            alert_type=AlertType.TENDER_CLOSING_SOON,
            severity=severity,
            title=f"Tender closing soon ({days_left}d): {t.title[:100] if t.title else org}",
            message=f"{org} — closes {t.closing_date.date().isoformat()} ({days_left} day(s) left).",
            # Stamp the closing date so a genuinely different close never dedups away.
            dedup_key=f"tender:{t.id}:CLOSING_SOON:{t.closing_date.date().isoformat()}",
            company_id=t.company_id or t.target_company_id,
            tender_id=t.id,
            source_id=t.source_id,
            link=f"/tenders",
        ))
    return findings


def detect_tender_findings(
    session: Session, *, now: datetime, run_since: datetime | None = None,
    config: TenderMonitorConfig = DEFAULT_TENDER_MONITOR,
) -> list[Finding]:
    """All tender findings for one monitoring cycle."""
    return detect_new_tenders(session, now=now, run_since=run_since) + \
        detect_closing_soon(session, now=now, config=config)
