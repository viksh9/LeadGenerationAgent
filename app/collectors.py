"""Unified real-source collection CLI (Prompt 46 §41, §42).

    python -m app.collectors list
    python -m app.collectors run --source adzuna
    python -m app.collectors run --source jooble --dry-run
    python -m app.collectors run --all --dry-run

Dispatches to the SourceOrchestrator, which reuses the same collector/pipeline
services as the app (no duplicate ingestion). Only implemented + configured sources
actually collect; everything else reports its honest status. ``run`` persists real
records; ``--dry-run`` makes the real request and validates it but persists nothing.
Never fabricates data on failure (§50).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from config.dotenv import load_dotenv  # noqa: E402

load_dotenv()

from config import get_settings  # noqa: E402
from collectors.orchestrator import SourceOrchestrator  # noqa: E402
from collectors.registry import runnable_source_ids  # noqa: E402
from collectors.source_status import all_source_status  # noqa: E402
from database.session import create_session_factory, get_engine, init_db  # noqa: E402

EXIT_OK = 0
EXIT_ERROR = 1
EXIT_NOT_CONFIGURED = 2


def _session():
    engine = get_engine(get_settings().database_url)
    init_db(engine)
    return create_session_factory(engine)()


def _all_source_ids() -> list[str]:
    return [r.source_id for r in all_source_status()]


def cmd_list(_args) -> int:
    runnable = runnable_source_ids()
    print(f"{'SOURCE':26}{'CATEGORY':20}{'RUNNABLE':10}{'STATUS'}")
    for r in all_source_status():
        status = r.status.value if hasattr(r.status, "value") else str(r.status)
        cat = getattr(r.category, "value", str(r.category))
        print(f"{r.source_id:26}{cat:20}{('yes' if r.source_id in runnable else 'no'):10}{status}")
    return EXIT_OK


def cmd_run(args) -> int:
    persist = not args.dry_run
    with _session() as session:
        orch = SourceOrchestrator(session)
        if args.all:
            source_ids = sorted(runnable_source_ids())
        else:
            if not args.source:
                print("ERROR: provide --source <id> or --all")
                return EXIT_ERROR
            source_ids = [args.source]

        results = orch.run(source_ids, dry_run=args.dry_run, persist=persist,
                           max_records=args.max_records)
        if persist:
            session.commit()

        if args.json:
            print(json.dumps([r.as_dict() for r in results], indent=2))
        else:
            for r in results:
                print(f"  {r.source_id:20} {r.status:22} recv={r.records_received} "
                      f"persisted={r.records_persisted} dup={r.duplicates}  {r.detail or ''}")

        # Exit code reflects the single-source case; --all always returns OK if it ran.
        if not args.all and results:
            st = results[0].status
            if st in ("COLLECTED", "DRY_RUN_OK", "MANUAL_SOURCE_REQUIRED"):
                return EXIT_OK
            if st == "NOT_CONFIGURED":
                return EXIT_NOT_CONFIGURED
            return EXIT_ERROR
        return EXIT_OK


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m app.collectors",
                                     description="Run real-data source collectors.")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("list", help="List sources + runnable/status.")
    p = sub.add_parser("run", help="Collect from a source (or --all).")
    p.add_argument("--source", help="Source id (adzuna, jooble, greenhouse, lever, ...).")
    p.add_argument("--all", action="store_true", help="Run all runnable sources (isolated).")
    p.add_argument("--dry-run", action="store_true", help="Real request, validate, DO NOT persist.")
    p.add_argument("--max-records", type=int, default=50)
    p.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    if args.command == "list":
        return cmd_list(args)
    return cmd_run(args)


if __name__ == "__main__":
    raise SystemExit(main())
