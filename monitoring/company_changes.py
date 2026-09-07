"""Company-level change detection (§9).

Aggregates REAL signals into ``CompanyChangeEvent`` rows + Findings: hiring
activity trend, new technology demand (surge), new verified decision-makers, and
newly observed project/tender business signals. Everything derives from real
records; the surge/trend thresholds are configurable. Idempotent via dedup keys
stamped with the comparison period so re-runs don't duplicate.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from database.models import (
    AlertSeverity,
    AlertType,
    BusinessSignal,
    ChangeSignificance,
    Company,
    CompanyChangeEvent,
    DataProvenance,
    DecisionMaker,
    VerificationStatus,
)
from monitoring.config import DEFAULT_MONITORING, MonitoringConfig
from monitoring.findings import Finding
from monitoring.trends import (
    detect_hiring_surge_for_company,
    detect_technology_surges_for_company,
    hiring_trend_for_company,
)

_PROJECT_SIGNAL_TYPES = {
    "PROJECT_AWARD", "PROJECT_EXECUTION", "CONTRACT", "IT_CONTRACT",
    "DIGITAL_TRANSFORMATION", "CLOUD_MIGRATION", "TECHNOLOGY_MODERNIZATION",
    "SYSTEM_IMPLEMENTATION", "TECH_CENTER_EXPANSION", "DELIVERY_CENTER_EXPANSION",
    "ENGINEERING_EXPANSION",
}
_VERIFIED = {VerificationStatus.VERIFIED.value, VerificationStatus.PARTIALLY_VERIFIED.value}


@dataclass
class CompanyChangeSummary:
    events: list[CompanyChangeEvent] = field(default_factory=list)
    findings: list[Finding] = field(default_factory=list)


def _status_value(status) -> str:
    return status.value if hasattr(status, "value") else str(status)


def _exists(session: Session, dedup_key: str) -> bool:
    return session.execute(
        select(CompanyChangeEvent.id).where(CompanyChangeEvent.dedup_key == dedup_key)
    ).scalars().first() is not None


def detect_company_changes(
    session: Session,
    *,
    now: datetime,
    run_since: datetime | None = None,
    scheduler_run_id: int | None = None,
    config: MonitoringConfig = DEFAULT_MONITORING,
) -> CompanyChangeSummary:
    """Detect and persist company-level changes across REAL companies."""
    summary = CompanyChangeSummary()
    period_stamp = (now - timedelta(days=config.hiring_surge.period_days)).date().isoformat()

    companies = session.execute(
        select(Company).where(Company.data_provenance == DataProvenance.REAL)
    ).scalars().all()

    for company in companies:
        norm = company.normalized_name
        if not norm:
            continue

        # --- Hiring surge / trend ---
        surge = detect_hiring_surge_for_company(session, norm, now=now, config=config.hiring_surge)
        if surge.is_surge:
            key = f"company:{company.id}:HIRING_SURGE:{period_stamp}"
            if not _exists(session, key):
                summary.events.append(CompanyChangeEvent(
                    company_id=company.id, change_type="HIRING_ACTIVITY_INCREASED",
                    summary=surge.detail, old_state=str(surge.previous), new_state=str(surge.current),
                    significance=ChangeSignificance.HIGH, scheduler_run_id=scheduler_run_id, dedup_key=key,
                ))
                summary.findings.append(Finding(
                    alert_type=AlertType.HIRING_SURGE, severity=AlertSeverity.HIGH,
                    title=f"Hiring surge: {company.canonical_name}",
                    message=surge.detail, dedup_key=key, company_id=company.id,
                    link=f"/companies/{company.canonical_name}",
                ))

        # --- Technology demand surges ---
        for tech in detect_technology_surges_for_company(
            session, norm, now=now, tracked=config.tracked_technologies, config=config.tech_surge
        ):
            key = f"company:{company.id}:{tech.label}:{period_stamp}"
            if _exists(session, key):
                continue
            summary.events.append(CompanyChangeEvent(
                company_id=company.id, change_type="NEW_TECHNOLOGY_DEMAND",
                summary=tech.detail, old_state=str(tech.previous), new_state=str(tech.current),
                significance=ChangeSignificance.MEDIUM, scheduler_run_id=scheduler_run_id, dedup_key=key,
            ))
            summary.findings.append(Finding(
                alert_type=AlertType.NEW_TECHNOLOGY_SIGNAL, severity=AlertSeverity.MEDIUM,
                title=f"Technology demand surge: {company.canonical_name}",
                message=tech.detail, dedup_key=key, company_id=company.id,
                link=f"/companies/{company.canonical_name}",
            ))

        # --- New verified decision-makers ---
        if run_since is not None:
            new_dms = session.execute(
                select(DecisionMaker).where(
                    DecisionMaker.company_id == company.id,
                    DecisionMaker.data_provenance == DataProvenance.REAL,
                    DecisionMaker.first_seen_at >= run_since,
                )
            ).scalars().all()
            for dm in new_dms:
                if _status_value(dm.verification_status) not in _VERIFIED:
                    continue
                key = f"company:{company.id}:DM:{dm.id}"
                if _exists(session, key):
                    continue
                summary.events.append(CompanyChangeEvent(
                    company_id=company.id, change_type="DECISION_MAKER_ADDED",
                    summary=f"New verified decision-maker: {dm.full_name or dm.job_title}",
                    new_state=(dm.job_title or dm.full_name),
                    significance=ChangeSignificance.MEDIUM, scheduler_run_id=scheduler_run_id, dedup_key=key,
                ))
                summary.findings.append(Finding(
                    alert_type=AlertType.NEW_DECISION_MAKER, severity=AlertSeverity.MEDIUM,
                    title=f"New decision-maker: {company.canonical_name}",
                    message=f"{dm.full_name or 'Contact'} — {dm.job_title or 'role'}.",
                    dedup_key=key, company_id=company.id,
                    link=f"/companies/{company.canonical_name}",
                ))

    # --- New project business signals (§15 project announcements) ---
    if run_since is not None:
        summary_findings, summary_events = _detect_new_projects(session, run_since=run_since,
                                                                scheduler_run_id=scheduler_run_id)
        summary.findings.extend(summary_findings)
        summary.events.extend(summary_events)

    if summary.events:
        for ev in summary.events:
            session.add(ev)
        session.flush()
    return summary


def _detect_new_projects(
    session: Session, *, run_since: datetime, scheduler_run_id: int | None,
) -> tuple[list[Finding], list[CompanyChangeEvent]]:
    signals = session.execute(
        select(BusinessSignal).where(
            BusinessSignal.data_provenance == DataProvenance.REAL,
            BusinessSignal.collected_at >= run_since,
        )
    ).scalars().all()
    findings: list[Finding] = []
    events: list[CompanyChangeEvent] = []
    for sig in signals:
        stype = _status_value(sig.signal_type)
        if stype not in _PROJECT_SIGNAL_TYPES:
            continue
        key = f"signal:{sig.id}:NEW_PROJECT"
        exists = session.execute(
            select(CompanyChangeEvent.id).where(CompanyChangeEvent.dedup_key == key)
        ).scalars().first()
        if exists:
            continue
        findings.append(Finding(
            alert_type=AlertType.NEW_PROJECT, severity=AlertSeverity.HIGH,
            title=f"New project signal: {sig.company_name or 'company'}",
            message=(sig.signal_title or stype)[:255],
            dedup_key=key, company_id=sig.company_id, signal_id=sig.id, link="/signals",
        ))
        if sig.company_id:
            events.append(CompanyChangeEvent(
                company_id=sig.company_id, change_type="PROJECT_SIGNAL",
                summary=(sig.signal_title or stype)[:255], new_state=stype,
                significance=ChangeSignificance.HIGH, scheduler_run_id=scheduler_run_id, dedup_key=key,
            ))
    return findings, events
