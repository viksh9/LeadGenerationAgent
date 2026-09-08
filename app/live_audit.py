"""Live (opt-in, network) audits (Prompt 41 §7, §8, §9, §21).

These make REAL requests to configured sources. They are only invoked by their own
CLI subcommands — never during offline audits. They NEVER fabricate business
records: if live access fails, they report the failure and persist nothing. Live
ingestion persists real records ONLY with an explicit ``--persist`` flag.
"""

from __future__ import annotations

import time

from sqlalchemy import select
from sqlalchemy.orm import Session

from database.models import DataProvenance, EvidenceRecord, Lead


# --------------------------------------------------------------------------- #
# §7 — live source connectivity
# --------------------------------------------------------------------------- #
def live_sources(session: Session, *, only: str | None = None) -> list[dict]:
    """Run a REAL connectivity check for each configured, runnable source.
    Persists SourceHealth (a real check result), creates NO business records."""
    from collectors.connectivity import check_source_connection
    from collectors.registry import build_collector, runnable_source_ids

    results: list[dict] = []
    for source_id in sorted(runnable_source_ids()):
        if only and source_id != only:
            continue
        # Config gate first — never make a network call for an unconfigured source.
        try:
            collector = build_collector(source_id)
        except Exception as exc:  # noqa: BLE001
            results.append({"source_id": source_id, "status": "NOT_IMPLEMENTED",
                            "detail": f"{type(exc).__name__}", "performed_request": False})
            continue
        config = getattr(collector, "config", None)
        if config is not None and hasattr(config, "is_configured") and not config.is_configured:
            results.append({"source_id": source_id, "status": "NOT_CONFIGURED",
                            "detail": "no credentials", "performed_request": False})
            continue

        started = time.monotonic()
        try:
            check = check_source_connection(session, source_id)
            session.commit()
            results.append({
                "source_id": source_id,
                "status": check.status.value if hasattr(check.status, "value") else str(check.status),
                "detail": check.message, "performed_request": check.performed_request,
                "latency_ms": int((time.monotonic() - started) * 1000),
            })
        except Exception as exc:  # noqa: BLE001
            session.rollback()
            results.append({"source_id": source_id, "status": "ERROR",
                            "detail": f"{type(exc).__name__}", "performed_request": True})
    return results


# --------------------------------------------------------------------------- #
# §8/§9 — live ingestion smoke (safe by default: dry-run)
# --------------------------------------------------------------------------- #
def live_ingestion(session: Session, *, source_id: str, persist: bool = False,
                   max_records: int = 20) -> dict:
    """Fetch a small real sample from ``source_id`` and (optionally) run it through
    the real pipeline. ``persist=False`` (default) does not write business records.
    On any live failure, nothing is fabricated."""
    from collectors.base import FetchRequest
    from collectors.errors import CollectorError, SourceAuthError, SourceRateLimitError, SourceUnavailableError
    from collectors.registry import CollectorNotImplemented, build_collector

    result: dict = {"source_id": source_id, "persist": persist, "dry_run": not persist}
    try:
        collector = build_collector(source_id)
    except (CollectorNotImplemented, CollectorError) as exc:
        result.update({"status": "NOT_AVAILABLE", "detail": str(exc)})
        return result

    config = getattr(collector, "config", None)
    if config is not None and hasattr(config, "is_configured") and not config.is_configured:
        result.update({"status": "NOT_CONFIGURED", "detail": "no credentials; nothing fetched"})
        return result

    # A single, small request.
    req = [FetchRequest(page=1, limit=max_records)]
    try:
        fetched = collector.fetch(req[0])
    except SourceAuthError as exc:
        result.update({"status": "AUTH_FAILED", "detail": str(exc)})
        return result
    except (SourceRateLimitError, SourceUnavailableError) as exc:
        result.update({"status": "TRANSIENT_FAILURE", "detail": str(exc)})
        return result
    except Exception as exc:  # noqa: BLE001
        result.update({"status": "ERROR", "detail": f"{type(exc).__name__}: {exc}"[:300]})
        return result

    records = list(fetched.records or [])[:max_records]
    result["records_received"] = len(records)

    if not persist:
        result.update({"status": "DRY_RUN_OK",
                       "detail": f"fetched {len(records)} real record(s); nothing persisted"})
        return result

    # Explicit persist: use the SAME services the app uses; snapshot before/after.
    from collectors.service import JobCollectionService
    from ingestion.job_pipeline import run_company_pipeline
    from app.report import real_data_scorecard

    before = real_data_scorecard(session)
    summary = JobCollectionService(session).collect(collector, req, record_run=True)
    run_company_pipeline(session, provenance=DataProvenance.REAL)
    session.commit()
    after = real_data_scorecard(session)
    result.update({
        "status": "PERSISTED",
        "accepted": summary.accepted, "skipped_duplicates": summary.skipped_duplicates,
        "before": before, "after": after,
    })
    return result


# --------------------------------------------------------------------------- #
# §21/§59 — trace one real lead end-to-end
# --------------------------------------------------------------------------- #
def trace_lead(session: Session, *, lead_id: int | None = None) -> dict:
    """Trace an ACTUAL real lead → evidence → source. Returns an honest 'none
    available' when no real lead exists — never fabricates one."""
    stmt = select(Lead).where(Lead.data_provenance == DataProvenance.REAL)
    if lead_id is not None:
        stmt = stmt.where(Lead.id == lead_id)
    else:
        stmt = stmt.order_by(Lead.lead_score.desc(), Lead.id.desc())
    lead = session.execute(stmt.limit(1)).scalars().first()
    if lead is None:
        return {"available": False,
                "message": "No real lead is currently available for trace demonstration."}

    evidence = session.execute(
        select(EvidenceRecord).where(EvidenceRecord.lead_id == lead.id)
        .order_by(EvidenceRecord.evidence_confidence.desc())
    ).scalars().all()

    return {
        "available": True,
        "lead": {
            "id": lead.id, "company": lead.company_name,
            "lead_score": lead.lead_score,
            "priority": getattr(lead.lead_priority, "value", str(lead.lead_priority)),
            "evidence_confidence": lead.evidence_confidence,
            "status": getattr(lead.status, "value", str(lead.status)),
            "signal_type": getattr(lead.signal_type, "value", None) if lead.signal_type else None,
            "source_name": lead.source_name, "source_url": lead.source_url,
            "provenance": getattr(lead.data_provenance, "value", str(lead.data_provenance)),
        },
        "evidence_chain": [
            {"id": e.id, "type": getattr(e.evidence_type, "value", str(e.evidence_type)),
             "source_name": e.source_name,
             "source_tier": getattr(e.source_tier, "value", str(e.source_tier)),
             "source_url": e.source_url,
             "verification_status": getattr(e.verification_status, "value", str(e.verification_status)),
             "observed_at": e.observed_at.isoformat() if e.observed_at else None}
            for e in evidence
        ],
        "evidence_count": len(evidence),
    }
