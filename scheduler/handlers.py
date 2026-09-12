"""Job-type handlers (§2). Each reuses existing collector/pipeline/monitoring
services — no duplicate ingestion logic. Handlers return a dict of REAL counters
that the scheduler records on the ``SchedulerRun`` audit row.

Network-touching handlers (collection, source-health check) are only invoked
when a job actually runs; normal tests exercise the no-network handlers or
monkeypatch collection. A source with no credentials raises ``SkipJob`` and
collects nothing — it never fabricates data.
"""

from __future__ import annotations

import logging
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from database.models import (
    DataProvenance,
    JobType,
    Lead,
    LeadPriority,
    ScheduledJob,
    VerificationStatus,
)
from monitoring.config import DEFAULT_MONITORING
from scheduler.errors import PermanentJobError, SkipJob, TransientJobError
from scheduler.reprocess import reprocess_lead, run_monitoring_cycle

logger = logging.getLogger(__name__)


# --------------------------------------------------------------------------- #
# Source collection (network). Mirrors scripts/collect.py internals exactly.
# --------------------------------------------------------------------------- #
def handle_source_collection(session: Session, job: ScheduledJob, now: datetime) -> dict:
    from collectors.base import FetchRequest
    from collectors.errors import (
        CollectorError,
        SourceAuthError,
        SourceRateLimitError,
        SourceUnavailableError,
    )
    from collectors.registry import CollectorNotImplemented, build_collector
    from collectors.service import JobCollectionService
    from collectors.source_budget import get_state as get_budget_state
    from collectors.source_budget import record_usage as record_budget_usage
    from ingestion.job_pipeline import run_company_pipeline

    source_id = job.source_id
    if not source_id:
        raise PermanentJobError("SOURCE_COLLECTION job has no source_id configured.")

    try:
        collector = build_collector(source_id)
    except CollectorNotImplemented as exc:
        raise PermanentJobError(f"collector not implemented: {exc}") from exc
    except CollectorError as exc:
        raise PermanentJobError(f"collector build failed: {exc}") from exc

    config = getattr(collector, "config", None)
    if config is not None and hasattr(config, "is_configured") and not config.is_configured:
        raise SkipJob(f"source '{source_id}' is NOT_CONFIGURED; nothing collected.")

    # Best-effort request plan (defaults; source config decides specifics).
    reqs = _plan(collector, job.config or {})

    budget_limit = getattr(config, "lifetime_request_budget", None) if config is not None else None
    if budget_limit:
        state = get_budget_state(session, source_id, budget=budget_limit)
        if state.exhausted:
            raise SkipJob(f"source '{source_id}' lifetime request budget exhausted.")
        reqs = reqs[: max(0, state.remaining)]
        if not reqs:
            raise SkipJob(f"source '{source_id}' has no remaining request budget.")

    svc = JobCollectionService(session)
    try:
        summary = svc.collect(collector, reqs, record_run=True)
    except SourceAuthError as exc:
        raise PermanentJobError(f"authentication failed for '{source_id}': {exc}") from exc
    except (SourceRateLimitError, SourceUnavailableError) as exc:
        raise TransientJobError(f"transient source failure for '{source_id}': {exc}") from exc

    if budget_limit:
        record_budget_usage(session, source_id, summary.requests, budget=budget_limit)

    run_company_pipeline(session, provenance=DataProvenance.REAL, now=now)

    # Detect job/company/tender changes from the freshly collected data.
    cycle = run_monitoring_cycle(
        session, now=now, run_since=job.last_success_at, config=DEFAULT_MONITORING, detect_jobs=True,
    )
    return {
        "records_fetched": summary.fetched,
        "records_new": summary.accepted,
        "records_unchanged": summary.skipped_duplicates,
        "records_changed": cycle.job_changes,
        "company_changes": cycle.company_changes,
        "alerts_generated": cycle.alerts_created,
    }


def _plan(collector, config: dict) -> list:
    from collectors.base import FetchRequest
    import inspect

    board = config.get("board")
    if board:
        return [FetchRequest(board=board, limit=config.get("per_page"))]
    query, location = config.get("query"), config.get("location")
    if query or location:
        pages = config.get("max_pages") or 1
        return [FetchRequest(query=query, location=location, page=p, limit=config.get("per_page"))
                for p in range(1, pages + 1)]
    if hasattr(collector, "plan_requests"):
        params = inspect.signature(collector.plan_requests).parameters
        kwargs = {}
        if "max_pages" in params:
            kwargs["max_pages"] = config.get("max_pages")
        if "mode" in params and config.get("mode"):
            kwargs["mode"] = config["mode"]
        if "max_requests" in params and config.get("max_requests"):
            kwargs["max_requests"] = config["max_requests"]
        return list(collector.plan_requests(**kwargs))
    return [FetchRequest(page=1, limit=config.get("per_page"))]


# --------------------------------------------------------------------------- #
# Monitoring / notification sweep (no network).
# --------------------------------------------------------------------------- #
def handle_monitoring_cycle(session: Session, job: ScheduledJob, now: datetime) -> dict:
    cycle = run_monitoring_cycle(
        session, now=now, run_since=job.last_success_at, config=DEFAULT_MONITORING, detect_jobs=True,
    )
    return {
        "records_changed": cycle.job_changes,
        "company_changes": cycle.company_changes,
        "source_health_events": cycle.source_health_events,
        "alerts_generated": cycle.alerts_created,
    }


def handle_tender_scan(session: Session, job: ScheduledJob, now: datetime) -> dict:
    from monitoring.tenders import detect_tender_findings
    from notifications.service import NotificationService

    findings = detect_tender_findings(session, now=now, run_since=job.last_success_at,
                                      config=DEFAULT_MONITORING.tender)
    emit = NotificationService(session).emit(findings, now=now)
    return {"alerts_generated": emit.created_count}


# --------------------------------------------------------------------------- #
# Evidence re-verification (§18): prioritized, not everything.
# --------------------------------------------------------------------------- #
def handle_evidence_reverification(session: Session, job: ScheduledJob, now: datetime) -> dict:
    limit = int((job.config or {}).get("limit", 50))
    leads = _prioritized_leads_for_reverification(session, limit=limit)
    changed = 0
    alerts = 0
    for lead in leads:
        res = reprocess_lead(session, lead.id, now=now, reverify=True, rescore=False)
        if res.changed:
            changed += 1
        alerts += len(res.alerts)
    return {"leads_changed": changed, "alerts_generated": alerts}


def _prioritized_leads_for_reverification(session: Session, *, limit: int) -> list[Lead]:
    """Prioritize high-value + stale + conflicted leads (§18); never re-fetch
    everything (§42)."""
    hot = session.execute(
        select(Lead).where(
            Lead.data_provenance == DataProvenance.REAL,
            Lead.lead_priority.in_([LeadPriority.HOT, LeadPriority.WARM]),
        ).order_by(Lead.lead_score.desc()).limit(limit)
    ).scalars().all()
    stale = session.execute(
        select(Lead).where(
            Lead.data_provenance == DataProvenance.REAL,
            Lead.verification_status == VerificationStatus.STALE,
        ).limit(limit)
    ).scalars().all()
    seen: dict[int, Lead] = {}
    for lead in [*hot, *stale]:
        seen.setdefault(lead.id, lead)
    return list(seen.values())[:limit]


# --------------------------------------------------------------------------- #
# Recompute + AI re-analysis.
# --------------------------------------------------------------------------- #
def handle_opportunity_recomputation(session: Session, job: ScheduledJob, now: datetime) -> dict:
    from intelligence.company_signal_aggregator import build_opportunity_candidates

    summary = build_opportunity_candidates(session, provenance=DataProvenance.REAL, now=now)
    candidates = getattr(summary, "candidates", 0)
    changed = len(candidates) if hasattr(candidates, "__len__") else int(candidates or 0)
    return {"opportunities_changed": int(changed)}


def handle_signal_recomputation(session: Session, job: ScheduledJob, now: datetime) -> dict:
    from monitoring.company_changes import detect_company_changes
    from notifications.service import NotificationService

    summary = detect_company_changes(session, now=now, run_since=job.last_success_at,
                                     config=DEFAULT_MONITORING)
    emit = NotificationService(session).emit(summary.findings, now=now)
    return {"signals_changed": len(summary.events), "alerts_generated": emit.created_count}


def handle_ai_reanalysis(session: Session, job: ScheduledJob, now: datetime) -> dict:
    """Change-driven AI re-analysis (§36): only HOT/WARM leads that have a recent
    meaningful change event and no fresh AI result. Uses the context-hash cache."""
    from datetime import timedelta

    from ai import service as ai_service
    from database.models import LeadChangeEvent

    lookback = timedelta(seconds=int((job.config or {}).get("lookback_seconds", 86400)))
    since = now - lookback
    recent_lead_ids = session.execute(
        select(LeadChangeEvent.lead_id).where(LeadChangeEvent.detected_at >= since).distinct()
    ).scalars().all()
    analyzed = 0
    for lead_id in recent_lead_ids:
        lead = session.get(Lead, lead_id)
        if lead is None or lead.data_provenance != DataProvenance.REAL:
            continue
        if lead.lead_priority not in (LeadPriority.HOT, LeadPriority.WARM):
            continue
        try:
            ai_service.analyze_lead(session, lead)   # cached; deterministic if no provider
            analyzed += 1
        except Exception:  # AI never breaks the scheduler
            logger.warning("AI re-analysis failed for lead %s (non-fatal)", lead_id)
    return {"leads_changed": analyzed, "notes": {"ai_reanalyzed": analyzed}}


def handle_source_health_check(session: Session, job: ScheduledJob, now: datetime) -> dict:
    """Probe real source connectivity (network) then emit health transitions."""
    from collectors.connectivity import check_source_connection
    from collectors.registry import runnable_source_ids
    from monitoring.source_health import scan_source_health
    from notifications.service import NotificationService

    checked = 0
    for source_id in sorted(runnable_source_ids()):
        try:
            check_source_connection(session, source_id)
            checked += 1
        except Exception:
            logger.warning("connectivity check failed for %s (non-fatal)", source_id)
    summary = scan_source_health(session, now=now)
    emit = NotificationService(session).emit(summary.findings, now=now)
    return {"records_fetched": checked, "source_health_events": len(summary.events),
            "alerts_generated": emit.created_count}


def handle_company_reenrichment(session: Session, job: ScheduledJob, now: datetime) -> dict:
    """Change-driven ContactOut POC re-enrichment (§30). Runs ONLY when ContactOut is
    configured, and only for HOT/WARM real leads with a recent material change AND no
    fresh POC within the freshness window. Skips entirely (no network, no credits) when
    nothing qualifies or ContactOut is not configured — never enriches every cycle."""
    from datetime import timedelta

    from config import get_settings
    from database.models import LeadChangeEvent
    from enrichment.contactout_poc import discover_pocs_for_lead

    if get_settings().contactout_config_status != "CONFIGURED":
        raise SkipJob("ContactOut is not configured; POC re-enrichment skipped.")

    cfg = job.config or {}
    lookback = timedelta(seconds=int(cfg.get("lookback_seconds", 86400)))
    max_companies = int(cfg.get("max_companies_per_cycle", 25))   # credit-aware cap
    since = now - lookback
    recent_lead_ids = session.execute(
        select(LeadChangeEvent.lead_id).where(LeadChangeEvent.detected_at >= since).distinct()
    ).scalars().all()

    enriched = 0
    considered = 0
    for lead_id in recent_lead_ids:
        if considered >= max_companies:
            break
        lead = session.get(Lead, lead_id)
        if lead is None or lead.data_provenance != DataProvenance.REAL:
            continue
        if lead.lead_priority not in (LeadPriority.HOT, LeadPriority.WARM):
            continue
        considered += 1
        try:
            # force=False → the service reuses fresh cached POCs and only spends a
            # credit when the freshness window has expired.
            summary = discover_pocs_for_lead(session, lead, actor="SCHEDULER", now=now)
            if summary.status in ("ENRICHED",):
                enriched += 1
        except Exception:  # ContactOut never breaks the scheduler
            logger.warning("ContactOut re-enrichment failed for lead %s (non-fatal)", lead_id)
    if considered == 0:
        raise SkipJob("No changed HOT/WARM leads to re-enrich this cycle.")
    return {"leads_changed": enriched, "notes": {"pocs_reenriched": enriched, "considered": considered}}


HANDLERS = {
    JobType.SOURCE_COLLECTION: handle_source_collection,
    JobType.EVIDENCE_REVERIFICATION: handle_evidence_reverification,
    JobType.SIGNAL_RECOMPUTATION: handle_signal_recomputation,
    JobType.OPPORTUNITY_RECOMPUTATION: handle_opportunity_recomputation,
    JobType.AI_REANALYSIS: handle_ai_reanalysis,
    JobType.NOTIFICATION_DISPATCH: handle_monitoring_cycle,
    JobType.SOURCE_HEALTH_CHECK: handle_source_health_check,
    JobType.TENDER_DEADLINE_SCAN: handle_tender_scan,
    JobType.COMPANY_ENRICHMENT: handle_company_reenrichment,  # ContactOut POC re-enrichment (§30)
}


def get_handler(job_type: JobType):
    handler = HANDLERS.get(job_type)
    if handler is None:
        raise PermanentJobError(f"no handler registered for job type {job_type}")
    return handler
