"""Event-driven reprocessing + the no-network monitoring cycle (§34, §35, §36).

* ``run_monitoring_cycle`` — the deterministic detection + alerting sweep (job
  changes, company changes, tenders, source-health), with NO network calls. It
  is the core, fully testable path.
* ``reprocess_lead`` — re-verify + optionally re-score a single lead, then diff
  its before/after state into lead-change events + alerts (§34 steps 5–10).
* ``should_trigger_ai`` / ``maybe_reanalyze_ai`` — change-driven AI re-analysis
  (§36): AI runs only when meaningful context changed, and relies on the existing
  context-hash cache so unchanged data never re-hits a provider.

Reuses existing services only — no duplicate pipeline logic.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from database.models import (
    Alert,
    CompanyChangeEvent,
    DataProvenance,
    DecisionMaker,
    Lead,
    LeadChangeEvent,
    VerificationStatus,
    utcnow,
)
from monitoring.change_detection import detect_job_changes
from monitoring.company_changes import detect_company_changes
from monitoring.config import DEFAULT_MONITORING, MonitoringConfig
from monitoring.lead_changes import LeadState, diff_lead
from monitoring.source_health import scan_source_health
from monitoring.tenders import detect_tender_findings
from notifications.service import NotificationService

_VERIFIED = {VerificationStatus.VERIFIED.value, VerificationStatus.PARTIALLY_VERIFIED.value}


@dataclass
class MonitoringCycleResult:
    job_changes: int = 0
    company_changes: int = 0
    source_health_events: int = 0
    findings: int = 0
    alerts_created: int = 0
    leads_changed: int = 0

    def as_dict(self) -> dict:
        return {
            "job_changes": self.job_changes,
            "company_changes": self.company_changes,
            "source_health_events": self.source_health_events,
            "findings": self.findings,
            "alerts_created": self.alerts_created,
            "leads_changed": self.leads_changed,
        }


def run_monitoring_cycle(
    session: Session,
    *,
    now: datetime | None = None,
    run_since: datetime | None = None,
    scheduler_run_id: int | None = None,
    config: MonitoringConfig = DEFAULT_MONITORING,
    detect_jobs: bool = True,
) -> MonitoringCycleResult:
    """Run the full deterministic detection + alert sweep over REAL data. No
    network calls; safe to run in tests."""
    now = now or utcnow()
    result = MonitoringCycleResult()
    findings = []

    if detect_jobs:
        job_summary = detect_job_changes(
            session, now=now, run_since=run_since, scheduler_run_id=scheduler_run_id
        )
        result.job_changes = job_summary.total

    company_summary = detect_company_changes(
        session, now=now, run_since=run_since, scheduler_run_id=scheduler_run_id, config=config
    )
    result.company_changes = len(company_summary.events)
    findings.extend(company_summary.findings)

    findings.extend(detect_tender_findings(session, now=now, run_since=run_since, config=config.tender))

    health_summary = scan_source_health(session, now=now, scheduler_run_id=scheduler_run_id)
    result.source_health_events = len(health_summary.events)
    findings.extend(health_summary.findings)

    result.findings = len(findings)
    emit = NotificationService(session).emit(findings, now=now)
    result.alerts_created = emit.created_count
    return result


# --------------------------------------------------------------------------- #
# Lead reprocessing (§34 steps 5–10)
# --------------------------------------------------------------------------- #
def build_lead_state(session: Session, lead: Lead) -> LeadState:
    """Capture a lead's comparable state from REAL persisted fields."""
    from verification.service import EvidenceVerificationService

    conflicts = EvidenceVerificationService(session).get_lead_conflicts(lead.id)
    verified_contacts = 0
    if lead.company_id:
        rows = session.execute(
            select(DecisionMaker).where(
                DecisionMaker.company_id == lead.company_id,
                DecisionMaker.data_provenance == DataProvenance.REAL,
            )
        ).scalars().all()
        verified_contacts = sum(
            1 for d in rows
            if (d.verification_status.value if hasattr(d.verification_status, "value")
                else str(d.verification_status)) in _VERIFIED
        )
    return LeadState(
        lead_id=lead.id,
        company_id=lead.company_id,
        company_name=lead.company_name,
        lead_score=float(lead.lead_score or 0),
        lead_priority=(lead.lead_priority.value if hasattr(lead.lead_priority, "value") else str(lead.lead_priority)),
        evidence_confidence=int(lead.evidence_confidence or 0),
        verification_status=(lead.verification_status.value if hasattr(lead.verification_status, "value")
                             else str(lead.verification_status)),
        lead_readiness=(lead.lead_readiness.value if hasattr(lead.lead_readiness, "value")
                        else str(lead.lead_readiness)),
        conflict_count=len(conflicts),
        verified_contact_count=verified_contacts,
    )


@dataclass
class LeadReprocessResult:
    lead_id: int
    changed: bool = False
    events: list[LeadChangeEvent] = field(default_factory=list)
    alerts: list[Alert] = field(default_factory=list)
    ai_triggered: bool = False


def reprocess_lead(
    session: Session,
    lead_id: int,
    *,
    now: datetime | None = None,
    reverify: bool = True,
    rescore: bool = False,
    config: MonitoringConfig = DEFAULT_MONITORING,
) -> LeadReprocessResult:
    """Re-verify (and optionally re-score) a lead, diff before/after, and emit
    lead-change events + alerts. AI re-analysis is triggered only when the change
    is meaningful (§36)."""
    from verification.service import EvidenceVerificationService

    now = now or utcnow()
    lead = session.get(Lead, lead_id)
    if lead is None:
        return LeadReprocessResult(lead_id=lead_id)

    before = build_lead_state(session, lead)

    if rescore:
        from intelligence.lead_pipeline import LeadAnalysisPipeline
        LeadAnalysisPipeline().reanalyze(session, lead_id)
    if reverify:
        EvidenceVerificationService(session).verify_lead(lead, now=now, persist=True)

    session.flush()
    session.refresh(lead)
    after = build_lead_state(session, lead)

    events, findings = diff_lead(before, after, now=now, config=config.lead_change)
    for ev in events:
        session.add(ev)
    if events:
        session.flush()
    emit = NotificationService(session).emit(findings, now=now)

    result = LeadReprocessResult(lead_id=lead_id, changed=bool(events), events=events, alerts=emit.created)
    if should_trigger_ai(events):
        result.ai_triggered = maybe_reanalyze_ai(session, lead)
    return result


# --------------------------------------------------------------------------- #
# Change-driven AI re-analysis (§36)
# --------------------------------------------------------------------------- #
_AI_TRIGGER_CHANGE_TYPES = {
    "PRIORITY_CHANGED", "SCORE_INCREASED", "CONFLICT_DETECTED", "EVIDENCE_STRENGTHENED",
}


def should_trigger_ai(lead_events: list[LeadChangeEvent]) -> bool:
    """AI re-analysis is warranted only on a meaningful change (§36) — never on
    unchanged/minor records."""
    from database.models import ChangeSignificance

    for ev in lead_events:
        ct = ev.change_type
        sig = ev.significance
        sig_val = sig.value if hasattr(sig, "value") else str(sig)
        if ct in _AI_TRIGGER_CHANGE_TYPES and sig_val in (
            ChangeSignificance.HIGH.value, ChangeSignificance.MEDIUM.value,
            ChangeSignificance.CRITICAL.value,
        ):
            return True
    return False


def maybe_reanalyze_ai(session: Session, lead: Lead) -> bool:
    """Trigger AI re-analysis for a lead. Uses the existing context-hash cache, so
    if nothing material changed the provider is not re-hit; and if no provider is
    configured this produces the deterministic grounded baseline (never fake)."""
    try:
        from ai import service as ai_service
        ai_service.analyze_lead(session, lead, force=True)
        return True
    except Exception:
        # AI must never break reprocessing; failure falls back silently to the
        # deterministic baseline already handled inside ai.service.
        return False
