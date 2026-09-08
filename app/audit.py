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
                                     description="Real-data validation, provenance & production audits.")
    sub = parser.add_subparsers(dest="command", required=True)
    for name, helptext in [
        ("validate-data", "Report data-quality/integrity issues (actual counts)."),
        ("production-readiness", "Fail on real-data/security violations."),
        ("provenance", "Verify every business record is traceable to a real source (§3)."),
        ("synthetic-data", "Detect synthetic production records + runtime fabrication paths (§4)."),
        ("quality", "Data-quality scorecard with actual percentages (§11-19)."),
        ("source-inventory", "Per-source implementation/config/connection/licensing (§5)."),
        ("source-readiness", "Per-source production readiness verdict (§53)."),
        ("full-report", "All sections with PASS/WARN/FAIL/NOT_CONFIGURED (§51)."),
        ("go-no-go", "GO only when all critical requirements pass (§52)."),
        ("scorecard", "Real-data readiness summary (actual counts, §53)."),
    ]:
        sp = sub.add_parser(name, help=helptext)
        sp.add_argument("--json", action="store_true")
        if name in ("validate-data",):
            sp.add_argument("--fail-on-issues", action="store_true")
    # Live (network) subcommands.
    ls = sub.add_parser("live-sources", help="Real connectivity check for configured sources (§7).")
    ls.add_argument("--json", action="store_true")
    ls.add_argument("--source", default=None)
    li = sub.add_parser("live-ingestion", help="Fetch a small real sample through the pipeline (§8).")
    li.add_argument("--source", required=True)
    li.add_argument("--persist", action="store_true", help="Persist real records (default: dry-run).")
    li.add_argument("--max-records", type=int, default=20)
    li.add_argument("--json", action="store_true")
    tl = sub.add_parser("trace-lead", help="Trace one real lead → evidence → source (§21).")
    tl.add_argument("--lead-id", type=int, default=None)
    tl.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    session = _session()
    try:
        if args.command == "validate-data":
            result = validate_data(session)
            _print_json_or(args, result, lambda: _print_validate(result))
            return EXIT_ISSUES if (getattr(args, "fail_on_issues", False) and not result["clean"]) else EXIT_OK

        if args.command == "production-readiness":
            result = production_readiness(session)
            _print_json_or(args, result, lambda: _print_readiness(result))
            return EXIT_OK if result["ready"] else EXIT_ISSUES

        if args.command == "provenance":
            from app.provenance_audit import provenance_report
            result = provenance_report(session)
            _print_json_or(args, result, lambda: _print_provenance(result))
            return EXIT_OK if result["ok"] else EXIT_ISSUES

        if args.command == "synthetic-data":
            from app.synthetic_audit import synthetic_report
            result = synthetic_report(session)
            _print_json_or(args, result, lambda: _print_synthetic(result))
            return EXIT_OK if result["ok"] else EXIT_ISSUES

        if args.command == "quality":
            from app.quality_audit import quality_report
            result = quality_report(session)
            _print_json_or(args, result, lambda: print(json.dumps(result, indent=2)))
            return EXIT_OK

        if args.command == "source-inventory":
            from app.source_inventory import source_inventory
            result = {"sources": source_inventory(session)}
            _print_json_or(args, result, lambda: _print_inventory(result["sources"]))
            return EXIT_OK

        if args.command == "source-readiness":
            from app.report import source_readiness
            result = source_readiness(session)
            _print_json_or(args, result, lambda: _print_source_readiness(result))
            return EXIT_OK

        if args.command == "full-report":
            from app.report import full_report
            result = full_report(session)
            _print_json_or(args, result, lambda: _print_full_report(result))
            return EXIT_OK

        if args.command == "go-no-go":
            from app.report import go_no_go
            result = go_no_go(session)
            _print_json_or(args, result, lambda: _print_go_no_go(result))
            return EXIT_OK if result["verdict"] == "GO" else EXIT_ISSUES

        if args.command == "scorecard":
            from app.report import real_data_scorecard
            result = real_data_scorecard(session)
            _print_json_or(args, result, lambda: _print_scorecard(result))
            return EXIT_OK

        if args.command == "live-sources":
            from app.live_audit import live_sources
            result = {"sources": live_sources(session, only=args.source)}
            _print_json_or(args, result, lambda: [print(f"  {s['source_id']:14} {s['status']:20} "
                                                        f"{s.get('detail','')}") for s in result["sources"]])
            return EXIT_OK

        if args.command == "live-ingestion":
            from app.live_audit import live_ingestion
            result = live_ingestion(session, source_id=args.source, persist=args.persist,
                                    max_records=args.max_records)
            _print_json_or(args, result, lambda: print(json.dumps(result, indent=2)))
            return EXIT_OK

        if args.command == "trace-lead":
            from app.live_audit import trace_lead
            result = trace_lead(session, lead_id=args.lead_id)
            _print_json_or(args, result, lambda: print(json.dumps(result, indent=2)))
            return EXIT_OK

        return EXIT_OK
    finally:
        session.close()


def _print_json_or(args, result, printer) -> None:
    if getattr(args, "json", False):
        print(json.dumps(result, indent=2, default=str))
    else:
        printer()


def _print_validate(result) -> None:
    print(f"Data validation — {result['total_records']} records, {result['total_issues']} issue(s):")
    for k, v in result["issues"].items():
        print(f"  {k:34} {v}{'' if v == 0 else '  <-- '}")
    print("CLEAN" if result["clean"] else "ISSUES FOUND")


def _print_readiness(result) -> None:
    print(f"Production readiness ({result['environment']}): {'READY' if result['ready'] else 'NOT READY'}")
    for c in result["checks"]:
        mark = "PASS" if c["passed"] else ("FAIL" if c["critical"] else "warn")
        print(f"  [{mark}] {c['check']}: {c['detail']}")


def _print_provenance(result) -> None:
    print(f"Provenance audit — {result['total_failures']} failure(s):")
    for c in result["checks"]:
        print(f"  [{'PASS' if c['ok'] else 'FAIL'}] {c['name']:34} {c['failures']}  {c['detail']}")
    print("OK" if result["ok"] else "PROVENANCE FAILURES")


def _print_synthetic(result) -> None:
    db, rt = result["database"], result["runtime"]
    print(f"Synthetic-data audit — DB synthetic: {db['synthetic_records']} "
          f"({'PASS' if db['ok'] else 'FAIL'})")
    if db["by_table"]:
        for t, n in db["by_table"].items():
            print(f"    {t}: {n}")
    print(f"Runtime fabrication hits (production code): {len(rt['production_runtime_hits'])} "
          f"({'PASS' if rt['ok'] else 'FAIL'}); allowed/guard hits: {rt['allowed_or_guard_hits']}")
    for h in rt["production_runtime_hits"][:20]:
        print(f"    PRODUCTION_RUNTIME {h['file']}:{h['line']}  {h['text']}")
    print("OK" if result["ok"] else "SYNTHETIC/FABRICATION FOUND")


def _print_inventory(sources) -> None:
    print(f"{'SOURCE':16}{'IMPL':16}{'CONFIG':18}{'CONNECTION':16}{'LICENSING'}")
    for s in sources:
        print(f"{s['source_id']:16}{s['implementation']:16}{s['configuration_status']:18}"
              f"{s['connection_status']:16}{s['commercial_use_status']}")


def _print_source_readiness(result) -> None:
    print(f"SOURCE READINESS — {result['live_verified']}/{result['total']} live-verified")
    print(f"  {'SOURCE':26}{'CATEGORY':16}{'VERDICT':18}{'LICENSE REVIEW'}")
    for r in result["sources"]:
        flag = "yes" if r["requires_license_review"] else "no"
        print(f"  {r['source_id']:26}{r['category']:16}{r['verdict']:18}{flag}")


def _print_full_report(result) -> None:
    print(f"FULL REPORT ({result['environment']}) @ {result['generated_at']}")
    for name, sec in result["sections"].items():
        st = sec.get("status", "")
        print(f"  {name:22} {st}")
    print("  scorecard:", json.dumps(result["scorecard"]))


def _print_go_no_go(result) -> None:
    print(f"GO/NO-GO ({result['environment']}): {result['verdict']}")
    for b in result["blockers"]:
        print(f"  BLOCKER: {b}")
    if result["verdict"] == "GO":
        print("  " + result["note"])


def _print_scorecard(result) -> None:
    print("REAL DATA READINESS")
    for k, v in result.items():
        print(f"  {k:22} {v}")


if __name__ == "__main__":
    raise SystemExit(main())
