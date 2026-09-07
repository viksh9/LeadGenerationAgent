#!/usr/bin/env python3
"""Generic real-data collection CLI: run a source collector and persist raw records.

    python scripts/collect.py --source adzuna
    python scripts/collect.py --source jooble --query "python developer" --location Bengaluru
    python scripts/collect.py --source adzuna --max-pages 2 --dry-run
    python scripts/collect.py --list

Behaviour (real-data-only):
  * Unknown source  -> error, exit 1.
  * No runnable collector for the source -> NOT_IMPLEMENTED, exit 3.
  * Source not configured (missing credentials) -> NOT_CONFIGURED, exit 2.
  * Configured -> real request, persist REAL raw records, optionally aggregate into
    company leads, and print the ACTUAL number collected. Never inserts dummy data.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from config.dotenv import load_dotenv  # noqa: E402

load_dotenv()

from collectors.base import FetchRequest  # noqa: E402
from collectors.errors import CollectorError  # noqa: E402
from collectors.registry import CollectorNotImplemented, build_collector, runnable_source_ids  # noqa: E402
from collectors.service import JobCollectionService  # noqa: E402
from collectors.career_source_registry import provider_for as career_provider_for  # noqa: E402
from collectors.career_source_registry import register_career_source  # noqa: E402
from collectors.source_budget import get_state as get_budget_state  # noqa: E402
from collectors.source_budget import record_usage as record_budget_usage  # noqa: E402
from database.models import CareerSourceStatus  # noqa: E402
from config import get_settings  # noqa: E402
from database.integrity import audit_database  # noqa: E402
from database.models import CollectionRun, DataProvenance  # noqa: E402
from database.session import create_session_factory, get_engine, init_db  # noqa: E402
from ingestion.ingestion_audit import build_ingestion_report, format_ingestion_report  # noqa: E402
from ingestion.job_pipeline import run_company_pipeline  # noqa: E402

EXIT_OK, EXIT_ERROR, EXIT_NOT_CONFIGURED, EXIT_NOT_IMPLEMENTED = 0, 1, 2, 3


def _plan(collector, args) -> list[FetchRequest]:
    # Explicit ATS board/site → one request for that board.
    if args.board:
        return [FetchRequest(board=args.board, limit=args.per_page)]
    if args.query or args.location:
        pages = args.max_pages or 1
        return [FetchRequest(query=args.query, location=args.location, page=p, limit=args.per_page)
                for p in range(1, pages + 1)]
    if hasattr(collector, "plan_requests"):
        kwargs = {"max_pages": args.max_pages}
        # Pass strategy controls to collectors that support them (e.g. Adzuna).
        import inspect
        params = inspect.signature(collector.plan_requests).parameters
        if "mode" in params and args.mode:
            kwargs["mode"] = args.mode
        if "max_requests" in params and args.max_requests:
            kwargs["max_requests"] = args.max_requests
        return collector.plan_requests(**kwargs)
    return [FetchRequest(page=1, limit=args.per_page)]


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    parser = argparse.ArgumentParser(description="Run a real-data source collector.")
    parser.add_argument("--source", help="Source id to collect (e.g. adzuna, jooble).")
    parser.add_argument("--list", action="store_true", help="List runnable sources and exit.")
    parser.add_argument("--query", help="Override search keyword.")
    parser.add_argument("--location", help="Override location.")
    parser.add_argument("--max-pages", type=int, help="Pages per query (default: source config).")
    parser.add_argument("--per-page", type=int, help="Results per page (default: source config).")
    parser.add_argument("--mode", choices=["ROLE_FIRST", "TECHNOLOGY_FIRST", "LOCATION_FIRST"],
                        help="Query strategy (Adzuna). Default: source config (ROLE_FIRST).")
    parser.add_argument("--max-requests", type=int,
                        help="Hard cap on API requests this run (default: source config).")
    parser.add_argument("--board",
                        help="ATS board token (Greenhouse) or site handle (Lever) to collect.")
    parser.add_argument("--dry-run", action="store_true", help="Fetch and report; persist nothing.")
    parser.add_argument("--skip-aggregate", action="store_true", help="Skip company-lead aggregation.")
    args = parser.parse_args(argv)

    if args.list or not args.source:
        print("Runnable sources:", ", ".join(sorted(runnable_source_ids())))
        return EXIT_OK if args.list else EXIT_ERROR

    try:
        collector = build_collector(args.source)
    except CollectorNotImplemented as exc:
        print(f"NOT_IMPLEMENTED: {exc}")
        return EXIT_NOT_IMPLEMENTED
    except CollectorError as exc:
        print(f"ERROR: {exc}")
        return EXIT_ERROR

    # Config gate — report NOT_CONFIGURED without a network call. An explicit
    # --board (ATS) provides the identifier for this run, so it satisfies the gate.
    config = getattr(collector, "config", None)
    if (not args.board and config is not None and hasattr(config, "is_configured")
            and not config.is_configured):
        print(f"NOT_CONFIGURED: source '{args.source}' has no credentials/board set "
              f"(see .env.example / docs/source-matrix.md). No data collected.")
        return EXIT_NOT_CONFIGURED

    settings = get_settings()
    engine = get_engine(settings.database_url)
    init_db(engine)
    reqs = _plan(collector, args)

    # Persistent lifetime request-budget guard (e.g. Jooble's 500/key free cap).
    budget_limit = getattr(config, "lifetime_request_budget", None) if config is not None else None
    started = time.monotonic()
    with create_session_factory(engine)() as session:
        if budget_limit:
            state = get_budget_state(session, args.source, budget=budget_limit)
            if state.exhausted:
                print(f"BUDGET_EXHAUSTED: source '{args.source}' has used its lifetime request "
                      f"budget ({state.used}/{state.budget}). Stopping cleanly; no requests made.")
                return EXIT_OK
            remaining = state.remaining or 0
            if len(reqs) > remaining:
                print(f"  budget: capping {len(reqs)} → {remaining} request(s) "
                      f"(used {state.used}/{state.budget} lifetime).")
                reqs = reqs[:remaining]
            if state.near_limit:
                print(f"  WARNING: approaching lifetime budget ({state.used}/{state.budget}).")

        print(f"Collecting '{args.source}': {len(reqs)} request(s)"
              f"{' [DRY RUN]' if args.dry_run else ''}…")
        try:
            summary = JobCollectionService(session).collect(collector, reqs, dry_run=args.dry_run)
        except CollectorError as exc:
            print(f"COLLECTION FAILED: {exc}. No records persisted.")
            return EXIT_ERROR
        # Real requests are made even on a dry run, so they consume quota — record
        # them against the persistent lifetime budget.
        if budget_limit:
            new_state = record_budget_usage(session, args.source, summary.requests, budget=budget_limit)
            print(f"  budget: {new_state.used}/{new_state.budget} lifetime requests used.")
        print(f"  requests={summary.requests} fetched={summary.fetched} "
              f"new_records={summary.accepted} duplicates={summary.skipped_duplicates} "
              f"errors={len(summary.errors)}")
        for w in summary.warnings[:5]:
            print(f"  warning: {w}")
        for e in summary.errors[:5]:
            print(f"  error: {e}")
        if args.dry_run:
            print("Dry run — nothing persisted.")
            return EXIT_OK
        # Register discovered ATS boards as CONNECTED (real request succeeded).
        provider = career_provider_for(args.source)
        if provider is not None and summary.accepted >= 0 and not summary.errors:
            boards = {r.board for r in reqs if r.board}
            for board in boards:
                register_career_source(session, ats_provider=provider, board_identifier=board,
                                       status=CareerSourceStatus.CONNECTED)
            if boards:
                print(f"  registered {len(boards)} {args.source} board(s) as CONNECTED.")
        if not args.skip_aggregate:
            result = run_company_pipeline(session, provenance=DataProvenance.REAL)
            duration = round(time.monotonic() - started, 2)
            report = build_ingestion_report(
                session, source_id=args.source, collection_summary=summary,
                pipeline_summary=result, provenance=DataProvenance.REAL,
                duration_seconds=duration,
            )
            print("\n--- Ingestion report (actual counts) ---")
            print(format_ingestion_report(report))
            # Persist the consolidated counts on the collection run for auditability.
            if summary.run_id is not None:
                run = session.get(CollectionRun, summary.run_id)
                if run is not None:
                    run.notes = json.dumps(report.as_dict())
                    session.commit()
        audit = audit_database(session)
        print(f"\nDB now: {audit.total_records} real record(s); synthetic={audit.synthetic_total}; "
              f"clean={audit.is_clean}")
    return EXIT_OK


if __name__ == "__main__":
    raise SystemExit(main())
