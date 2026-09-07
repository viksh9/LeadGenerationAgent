"""Scheduler CLI (Prompt 38 §40).

Drives the SAME collector/monitoring services the API and background runner use —
no duplicate ingestion logic. Existing manual collection (scripts/collect.py) is
unchanged and remains available.

Usage:
    python scripts/scheduler.py list                 # show jobs + status
    python scripts/scheduler.py seed                 # create default jobs (idempotent)
    python scripts/scheduler.py run <job_name>       # run one job now (MANUAL)
    python scripts/scheduler.py tick                 # run all currently-due jobs once
    python scripts/scheduler.py runs [--limit N]     # recent run audit
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from config.dotenv import load_dotenv  # noqa: E402

load_dotenv()

from sqlalchemy import select  # noqa: E402

from database.models import SchedulerRun  # noqa: E402
from database.session import create_session_factory, get_engine, init_db  # noqa: E402
from config import get_settings  # noqa: E402
from scheduler.service import SchedulerService  # noqa: E402

EXIT_OK = 0
EXIT_ERROR = 1

logger = logging.getLogger(__name__)


def _session():
    settings = get_settings()
    engine = get_engine(settings.database_url)
    init_db(engine)
    return create_session_factory(engine)()


def cmd_list(_args) -> int:
    with _session() as session:
        svc = SchedulerService(session)
        jobs = svc.list_jobs() or (svc.seed_default_jobs(), session.commit(), svc.list_jobs())[-1]
        print(f"{'JOB':32} {'TYPE':26} {'STATUS':10} {'ENABLED':7} NEXT_RUN")
        for j in jobs:
            print(f"{j.job_name:32} {j.job_type.value:26} {j.current_status.value:10} "
                  f"{str(j.enabled):7} {j.next_run_at}")
    return EXIT_OK


def cmd_seed(_args) -> int:
    with _session() as session:
        created = SchedulerService(session).seed_default_jobs()
        session.commit()
        print(f"Seeded {len(created)} new job(s). (idempotent — existing jobs untouched)")
    return EXIT_OK


def cmd_run(args) -> int:
    with _session() as session:
        svc = SchedulerService(session)
        job = svc.get_by_name(args.job_name)
        if job is None:
            print(f"ERROR: no job named '{args.job_name}'. Try: python scripts/scheduler.py list")
            return EXIT_ERROR
        run = svc.run_job(job, trigger="MANUAL")
        session.commit()
        print(f"{job.job_name}: {run.status.value} "
              f"(fetched={run.records_fetched} changed={run.records_changed} "
              f"alerts={run.alerts_generated}) {run.error or ''}")
    return EXIT_OK


def cmd_tick(_args) -> int:
    with _session() as session:
        runs = SchedulerService(session).tick()
        session.commit()
        print(f"Ran {len(runs)} due job(s):")
        for r in runs:
            print(f"  {r.job_name}: {r.status.value}")
    return EXIT_OK


def cmd_runs(args) -> int:
    with _session() as session:
        rows = session.execute(
            select(SchedulerRun).order_by(SchedulerRun.started_at.desc()).limit(args.limit)
        ).scalars().all()
        for r in rows:
            print(f"{r.started_at} {r.job_name:30} {r.status.value:9} "
                  f"dur={r.duration_seconds}s alerts={r.alerts_generated} {r.error or ''}")
    return EXIT_OK


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    parser = argparse.ArgumentParser(description="Control the continuous monitoring scheduler.")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("list", help="List scheduled jobs and status.")
    sub.add_parser("seed", help="Create the default job set (idempotent).")
    p_run = sub.add_parser("run", help="Run one job now (MANUAL trigger).")
    p_run.add_argument("job_name")
    sub.add_parser("tick", help="Run all currently-due jobs once.")
    p_runs = sub.add_parser("runs", help="Show recent run audit history.")
    p_runs.add_argument("--limit", type=int, default=20)
    args = parser.parse_args(argv)

    handlers = {
        "list": cmd_list, "seed": cmd_seed, "run": cmd_run, "tick": cmd_tick, "runs": cmd_runs,
    }
    return handlers[args.command](args)


if __name__ == "__main__":
    raise SystemExit(main())
