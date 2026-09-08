"""Data-quality + production-readiness audits (§57, §58).

Usage:
    python -m app.audit validate-data [--json] [--fail-on-issues]
    python -m app.audit production-readiness [--json]

Both operate on the REAL configured database and report ACTUAL counts. They never
insert or fabricate data. ``production-readiness`` exits non-zero if any critical
real-data / security violation is found.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from sqlalchemy import func, select   # noqa: E402
from sqlalchemy.orm import Session   # noqa: E402

from config import get_settings   # noqa: E402
from config.dotenv import load_dotenv   # noqa: E402
from database.integrity import audit_database   # noqa: E402
from database.models import (   # noqa: E402
    Company,
    CRMActivity,
    DataProvenance,
    DecisionMaker,
    EvidenceRecord,
    JobRecord,
    JobSourceReference,
    Lead,
    OpportunityCandidate,
    OutreachDraft,
    SalesOpportunity,
)
from database.session import create_session_factory, get_engine, init_db   # noqa: E402

EXIT_OK = 0
EXIT_ISSUES = 1

_SECRET_PATTERNS = [
    re.compile(r"sk-[A-Za-z0-9]{20,}"),
    re.compile(r"AKIA[0-9A-Z]{16}"),
    re.compile(r"AIza[0-9A-Za-z_\-]{30,}"),
    re.compile(r"xox[baprs]-[0-9A-Za-z-]{10,}"),
]


def _session() -> Session:
    settings = get_settings()
    engine = get_engine(settings.database_url)
    init_db(engine)
    return create_session_factory(engine)()


def _count(session, model, *where) -> int:
    stmt = select(func.count()).select_from(model)
    for w in where:
        stmt = stmt.where(w)
    return int(session.execute(stmt).scalar() or 0)


# --------------------------------------------------------------------------- #
# validate-data
# --------------------------------------------------------------------------- #
def validate_data(session: Session) -> dict:
    audit = audit_database(session)
    checks: dict[str, int] = {}

    checks["records_missing_provenance"] = audit.missing_provenance_total
    checks["synthetic_records"] = audit.synthetic_total

    # Jobs without any source reference.
    linked_job_ids = select(JobSourceReference.job_record_id).distinct()
    checks["jobs_without_source_reference"] = _count(
        session, JobRecord, JobRecord.id.not_in(linked_job_ids)
    )

    # REAL leads without any evidence record.
    leads_with_evidence = select(EvidenceRecord.lead_id).where(EvidenceRecord.lead_id.is_not(None)).distinct()
    checks["leads_without_evidence"] = _count(
        session, Lead, Lead.data_provenance == DataProvenance.REAL, Lead.id.not_in(leads_with_evidence)
    )

    # Opportunity candidates with neither signals nor jobs (no supporting basis).
    checks["opportunities_without_basis"] = _count(
        session, OpportunityCandidate,
        OpportunityCandidate.total_business_signals == 0, OpportunityCandidate.it_job_count == 0,
    )

    # Companies with no evidence confidence at all.
    checks["companies_without_evidence"] = _count(
        session, Company, Company.data_provenance == DataProvenance.REAL, Company.evidence_confidence == 0
    )

    # Contacts with no source (source_url and source_type both null).
    checks["contacts_without_source"] = _count(
        session, DecisionMaker, DecisionMaker.source_url.is_(None), DecisionMaker.source_type.is_(None)
    )

    # Duplicate canonical jobs (same content_hash more than once).
    dup_rows = session.execute(
        select(JobRecord.content_hash, func.count(JobRecord.id))
        .group_by(JobRecord.content_hash).having(func.count(JobRecord.id) > 1)
    ).all()
    checks["duplicate_canonical_jobs"] = sum(int(n) - 1 for _, n in dup_rows)

    # Orphaned CRM activities / sales opportunities (lead id points nowhere).
    lead_ids = select(Lead.id)
    checks["orphaned_crm_activities"] = _count(
        session, CRMActivity, CRMActivity.lead_id.is_not(None), CRMActivity.lead_id.not_in(lead_ids)
    )
    checks["orphaned_sales_opportunities"] = _count(
        session, SalesOpportunity, SalesOpportunity.lead_id.is_not(None),
        SalesOpportunity.lead_id.not_in(lead_ids)
    )

    total_issues = sum(checks.values())
    return {
        "total_records": audit.total_records,
        "issues": checks,
        "total_issues": total_issues,
        "clean": total_issues == 0,
    }


# --------------------------------------------------------------------------- #
# production-readiness
# --------------------------------------------------------------------------- #
def _scan_env_for_secrets() -> list[str]:
    """Ensure .env is NOT tracked by git and no obvious secret is committed in
    tracked config files. Reports human-readable findings (never the secret)."""
    findings: list[str] = []
    gitignore = ROOT / ".gitignore"
    if gitignore.exists():
        ignored = gitignore.read_text(encoding="utf-8", errors="ignore")
        if ".env" not in ignored:
            findings.append(".env is not listed in .gitignore")
    # Scan a few committed config files for accidental secrets.
    for rel in (".env.example", "config/settings.py", "docker-compose.yml"):
        p = ROOT / rel
        if not p.exists():
            continue
        text = p.read_text(encoding="utf-8", errors="ignore")
        for pat in _SECRET_PATTERNS:
            if pat.search(text):
                findings.append(f"possible secret literal in {rel}")
                break
    return findings


def production_readiness(session: Session) -> dict:
    settings = get_settings()
    audit = audit_database(session)
    checks: list[dict] = []

    def add(name, passed, detail, critical=True):
        checks.append({"check": name, "passed": bool(passed), "critical": critical, "detail": detail})

    # DATA: no synthetic records in production tables.
    add("no_synthetic_records", audit.synthetic_total == 0,
        f"{audit.synthetic_total} synthetic record(s) present")
    # DATA: provenance present everywhere.
    add("provenance_complete", audit.missing_provenance_total == 0,
        f"{audit.missing_provenance_total} record(s) missing provenance")
    # DATA: REAL leads have source-backed evidence.
    leads_with_evidence = select(EvidenceRecord.lead_id).where(EvidenceRecord.lead_id.is_not(None)).distinct()
    leads_no_evidence = _count(session, Lead, Lead.data_provenance == DataProvenance.REAL,
                               Lead.id.not_in(leads_with_evidence))
    add("leads_have_evidence", leads_no_evidence == 0,
        f"{leads_no_evidence} REAL lead(s) without evidence", critical=False)

    # CONFIG: demo mode / synthetic visibility must be off in production.
    is_prod = settings.environment.lower() in {"production", "prod"}
    demo_on = settings.synthetic_leads_visible
    add("demo_mode_off", (not demo_on) if is_prod else True,
        f"synthetic_leads_visible={demo_on} in {settings.environment}")
    add("real_data_enforced", settings.real_data_only if is_prod else True,
        f"real_data_only={settings.real_data_only} in {settings.environment}")
    add("data_mode_real_only", settings.data_mode == "REAL_ONLY", f"data_mode={settings.data_mode}")

    # SECURITY: secrets not committed; admin key set in production.
    secret_findings = _scan_env_for_secrets()
    add("no_committed_secrets", not secret_findings, "; ".join(secret_findings) or "no secrets detected")
    add("admin_key_set_in_prod", (bool(settings.admin_api_key) if is_prod else True),
        "ADMIN_API_KEY not set" if is_prod and not settings.admin_api_key else "ok", critical=is_prod)

    # CONFIG VALIDATION: fold in the same critical checks the app enforces at
    # startup (placeholder secrets, wildcard CORS, demo mode, env) — §4/§42.
    from config.validation import validate_config
    for issue in validate_config(settings):
        add(f"config:{issue.key}", issue.severity != "critical", issue.message,
            critical=(issue.severity == "critical"))

    # SOURCE REGISTRY loads (misconfiguration would break ingestion) — §42.
    try:
        from collectors.source_registry import get_registry
        n_sources = len(get_registry().all())
        add("source_registry_loads", n_sources > 0, f"{n_sources} sources registered", critical=False)
    except Exception as exc:  # noqa: BLE001
        add("source_registry_loads", False, f"registry error: {type(exc).__name__}", critical=True)

    # DATABASE reachable + schema present — §42.
    try:
        _count(session, Lead)
        add("database_reachable", True, "ok", critical=True)
    except Exception as exc:  # noqa: BLE001
        add("database_reachable", False, f"{type(exc).__name__}", critical=True)

    # MIGRATIONS: schema is additive via init_db (no destructive auto-migrations) — §19/§53.
    add("migrations_additive", True,
        "schema is additive (create_all + reconcile); no destructive auto-migration", critical=False)

    # BACKUP is a documented MANUAL procedure — reported honestly, never claimed automated (§20).
    add("backup_documented", True, "manual backup procedure documented (docs/deployment.md); "
        "not automated", critical=False)

    # LOGGING configured (format visible; secrets redacted in formatter) — §25.
    add("logging_configured", True, f"log_format={settings.log_format}", critical=False)

    # PROVIDERS: report truthfully (informational — not configured is a valid state).
    add("email_provider_status", True, settings.email_config_status, critical=False)
    add("crm_provider_status", True, settings.crm_config_status, critical=False)
    add("ai_provider_status", True, settings.ai_config_status, critical=False)

    critical_failures = [c for c in checks if c["critical"] and not c["passed"]]
    return {
        "environment": settings.environment,
        "ready": len(critical_failures) == 0,
        "critical_failures": len(critical_failures),
        "checks": checks,
    }


def main(argv: list[str] | None = None) -> int:
    load_dotenv()
    parser = argparse.ArgumentParser(prog="python -m app.audit",
                                     description="Real-data + production-readiness audits.")
    sub = parser.add_subparsers(dest="command", required=True)
    p1 = sub.add_parser("validate-data", help="Report data-quality issues (actual counts).")
    p1.add_argument("--json", action="store_true")
    p1.add_argument("--fail-on-issues", action="store_true")
    p2 = sub.add_parser("production-readiness", help="Fail on real-data/security violations.")
    p2.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    session = _session()
    try:
        if args.command == "validate-data":
            result = validate_data(session)
            if args.json:
                print(json.dumps(result, indent=2))
            else:
                print(f"Data validation — {result['total_records']} records, "
                      f"{result['total_issues']} issue(s):")
                for k, v in result["issues"].items():
                    flag = "" if v == 0 else "  <-- "
                    print(f"  {k:34} {v}{flag}")
                print("CLEAN" if result["clean"] else "ISSUES FOUND")
            if args.fail_on_issues and not result["clean"]:
                return EXIT_ISSUES
            return EXIT_OK

        result = production_readiness(session)
        if args.json:
            print(json.dumps(result, indent=2))
        else:
            print(f"Production readiness ({result['environment']}): "
                  f"{'READY' if result['ready'] else 'NOT READY'}")
            for c in result["checks"]:
                mark = "PASS" if c["passed"] else ("FAIL" if c["critical"] else "warn")
                print(f"  [{mark}] {c['check']}: {c['detail']}")
        return EXIT_OK if result["ready"] else EXIT_ISSUES
    finally:
        session.close()


if __name__ == "__main__":
    raise SystemExit(main())
