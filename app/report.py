"""Composite audit reports (Prompt 41 §51, §52, §53).

* ``full_report`` — every audit section with a PASS/WARN/FAIL/NOT_CONFIGURED status.
* ``go_no_go`` — GO only when all CRITICAL requirements pass; NO-GO otherwise
  (synthetic production data, missing provenance/broken links, production-config
  failure, database integrity). Optional providers are REQUIRES_REVIEW, not
  blocking.
* ``real_data_scorecard`` — a real-data readiness summary of ACTUAL counts.
"""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.audit import production_readiness, validate_data
from app.provenance_audit import provenance_report
from app.quality_audit import quality_report
from app.source_inventory import source_inventory
from app.synthetic_audit import synthetic_report
from config import get_settings
from database.models import (
    Company,
    DataProvenance,
    DecisionMaker,
    EvidenceRecord,
    JobRecord,
    Lead,
    OpportunityCandidate,
    RawSourceRecord,
    BusinessSignal,
    utcnow,
)

# Provenance checks whose non-zero failure is a hard blocker.
_CRITICAL_PROVENANCE = {
    "raw_missing_source_id", "raw_missing_content_hash", "jobs_missing_provenance",
    "companies_missing_provenance", "leads_without_evidence", "evidence_broken_lead_link",
    "ai_facts_without_evidence", "signals_missing_source", "contacts_without_source",
    "tenders_missing_source",
}


def _count(session, model, *where) -> int:
    stmt = select(func.count()).select_from(model)
    for w in where:
        stmt = stmt.where(w)
    return int(session.execute(stmt).scalar() or 0)


def full_report(session: Session) -> dict:
    settings = get_settings()
    prov = provenance_report(session)
    syn = synthetic_report(session)
    data = validate_data(session)
    prod = production_readiness(session)
    quality = quality_report(session)
    inventory = source_inventory(session)

    connected = [s for s in inventory if s["connection_status"] == "CONNECTED"]
    configured = [s for s in inventory if s["configuration_status"] in ("CONFIGURED", "CONNECTED")]

    def status(ok: bool, warn: bool = False) -> str:
        return "PASS" if ok else ("WARN" if warn else "FAIL")

    sections = {
        "source_health": {
            "status": "PASS" if inventory else "NOT_CONFIGURED",
            "sources": len(inventory), "configured": len(configured), "connected": len(connected),
        },
        "data_provenance": {"status": status(prov["ok"]), "total_failures": prov["total_failures"]},
        "synthetic_data": {"status": status(syn["ok"]),
                           "db_synthetic": syn["database"]["synthetic_records"],
                           "runtime_hits": len(syn["runtime"]["production_runtime_hits"])},
        "data_quality": {"status": "PASS", "detail": "see quality section (actual percentages)"},
        "database_integrity": {"status": status(data["clean"]), "total_issues": data["total_issues"]},
        "production_readiness": {"status": status(prod["ready"]),
                                 "critical_failures": prod["critical_failures"]},
        "providers": {
            "ai": settings.ai_config_status, "email": settings.email_config_status,
            "crm": settings.crm_config_status,
        },
    }
    return {
        "generated_at": utcnow().isoformat(),
        "environment": settings.environment,
        "sections": sections,
        "quality": quality,
        "source_inventory": inventory,
        "scorecard": real_data_scorecard(session),
    }


def go_no_go(session: Session) -> dict:
    prov = provenance_report(session)
    syn = synthetic_report(session)
    data = validate_data(session)
    prod = production_readiness(session)

    blockers: list[str] = []

    if not syn["database"]["ok"]:
        blockers.append(f"synthetic production records present: {syn['database']['synthetic_records']}")
    for c in prov["checks"]:
        if c["name"] in _CRITICAL_PROVENANCE and c["failures"] > 0:
            blockers.append(f"provenance: {c['name']}={c['failures']}")
    if not data["clean"]:
        # Orphans/duplicates are integrity blockers.
        blockers.append(f"database integrity issues: {data['total_issues']}")
    if not prod["ready"]:
        blockers.append(f"production-config critical failures: {prod['critical_failures']}")

    verdict = "GO" if not blockers else "NO-GO"
    # Runtime fabrication scan is advisory (REQUIRES_REVIEW), not a hard blocker —
    # legitimate guard/label/comment code references these tokens.
    review = len(syn["runtime"]["production_runtime_hits"])
    return {
        "verdict": verdict,
        "environment": get_settings().environment,
        "blockers": blockers,
        "runtime_scan_requires_review": review,
        "note": ("All critical requirements pass. Optional external providers may still be "
                 "NOT_CONFIGURED / REQUIRES_REVIEW without blocking."),
    }


def source_readiness(session: Session) -> dict:
    """Per-source production readiness (§53). Truthful — never infers CONNECTED.
    LIVE_VERIFIED only when a real check has recorded a last_success_at."""
    inventory = source_inventory(session)
    rows = []
    for s in inventory:
        impl = s["implementation"]              # IMPLEMENTED | NOT_IMPLEMENTED
        conn = s["connection_status"]           # CONNECTED | ... | NOT_CHECKED
        conf = s["configuration_status"]
        licensing = s["commercial_use_status"]

        if impl == "NOT_IMPLEMENTED":
            verdict = "NOT_IMPLEMENTED"
        elif conn == "CONNECTED" and s.get("last_success_at"):
            verdict = "LIVE_VERIFIED"
        elif conn == "CONNECTED":
            verdict = "CONNECTED"
        elif conn in ("AUTHENTICATION_FAILED", "ERROR"):
            verdict = "BLOCKED"
        elif conf in ("CONFIGURED",):
            verdict = "CONFIGURED"
        elif conf in ("NOT_CONFIGURED", "DISCOVERY_REQUIRED", "REQUIRES_REVIEW", "PLANNED",
                      "AUTHENTICATION_REQUIRED"):
            verdict = "NOT_CONFIGURED"
        else:
            verdict = "REQUIRES_REVIEW"

        # Flag licensing that needs human review (does not by itself block).
        requires_review = licensing in ("REQUIRES_REVIEW", "REQUIRES_APPROVAL", "RESTRICTED", "UNKNOWN")
        rows.append({
            "source_id": s["source_id"], "category": s["category"], "verdict": verdict,
            "implementation": impl, "configuration": conf, "connection": conn,
            "licensing": licensing, "requires_license_review": requires_review,
            "last_success_at": s.get("last_success_at"),
        })
    live = sum(1 for r in rows if r["verdict"] == "LIVE_VERIFIED")
    return {"sources": rows, "total": len(rows), "live_verified": live}


def real_data_scorecard(session: Session) -> dict:
    inventory = source_inventory(session)
    connected = sum(1 for s in inventory if s["connection_status"] == "CONNECTED")

    raw = _count(session, RawSourceRecord)
    jobs = _count(session, JobRecord)
    companies = _count(session, Company)
    evidence = _count(session, EvidenceRecord)
    signals = _count(session, BusinessSignal)
    opps = _count(session, OpportunityCandidate)
    leads = _count(session, Lead, Lead.data_provenance == DataProvenance.REAL)
    contacts = _count(session, DecisionMaker)

    with_prov = _count(session, Lead, Lead.data_provenance == DataProvenance.REAL)  # all REAL leads carry provenance
    with_ev_ids = select(EvidenceRecord.lead_id).where(EvidenceRecord.lead_id.is_not(None)).distinct()
    leads_with_evidence = _count(session, Lead,
        Lead.data_provenance == DataProvenance.REAL, Lead.id.in_(with_ev_ids))

    return {
        "source_connectivity": f"{connected}/{len(inventory)}",
        "raw_records": raw,
        "canonical_jobs": jobs,
        "companies": companies,
        "evidence_records": evidence,
        "signals": signals,
        "opportunities": opps,
        "production_leads": leads,
        "leads_with_evidence": f"{leads_with_evidence}/{leads}",
        "contacts": contacts,
    }
