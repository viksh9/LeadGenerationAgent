#!/usr/bin/env python3
"""Real source connectivity check CLI.

    python scripts/source_check.py --source adzuna
    python scripts/source_check.py --all

Performs a real, credential-based request for each runnable source and persists
the result to the source_health table (last checked/success/failure/error). A
source is reported CONNECTED only when a real request actually succeeds. Sources
without credentials report NOT_CONFIGURED and make NO network call.
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

from collectors.connectivity import check_source_connection  # noqa: E402
from collectors.errors import CollectorError  # noqa: E402
from collectors.registry import runnable_source_ids  # noqa: E402
from config import get_settings  # noqa: E402
from database.session import create_session_factory, get_engine, init_db  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    parser = argparse.ArgumentParser(description="Check real source connectivity and persist health.")
    parser.add_argument("--source", help="Source id to check.")
    parser.add_argument("--all", action="store_true", help="Check all runnable sources.")
    args = parser.parse_args(argv)

    if not args.source and not args.all:
        parser.error("provide --source <id> or --all")

    targets = sorted(runnable_source_ids()) if args.all else [args.source]
    settings = get_settings()
    engine = get_engine(settings.database_url)
    init_db(engine)

    rc = 0
    with create_session_factory(engine)() as session:
        for source_id in targets:
            try:
                result = check_source_connection(session, source_id)
            except CollectorError as exc:
                print(f"{source_id}: ERROR — {exc}")
                rc = 1
                continue
            net = "live request" if result.performed_request else "no network (config state)"
            print(f"{source_id}: {result.status.value} ({net})"
                  + (f" — {result.message}" if result.message else ""))
            if result.status.value not in {"CONNECTED", "NOT_CONFIGURED"}:
                rc = 1
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
