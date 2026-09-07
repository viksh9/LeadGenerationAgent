#!/usr/bin/env python3
"""Normalize pending raw source records into analyzed Leads.

Usage:
    python scripts/process_raw.py                 # process all NEW raw records
    python scripts/process_raw.py --limit 50      # process up to 50
    python scripts/process_raw.py --real-only     # skip synthetic raw records
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from config import get_settings  # noqa: E402
from database.session import create_session_factory, get_engine, init_db  # noqa: E402
from ingestion.processor import process_pending  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    parser = argparse.ArgumentParser(description="Normalize raw source records into Leads.")
    parser.add_argument("--limit", type=int, default=None, help="Max records to process.")
    parser.add_argument("--real-only", action="store_true", help="Skip synthetic raw records.")
    args = parser.parse_args(argv)

    settings = get_settings()
    engine = get_engine(settings.database_url)
    init_db(engine)
    session_factory = create_session_factory(engine)

    print(f"Processing raw records into leads ({settings.database_url})")
    with session_factory() as session:
        summary = process_pending(session, limit=args.limit, include_synthetic=not args.real_only)

    print(f"\nProcessed: {summary.processed}  Invalid: {summary.invalid}  Failed: {summary.failed}")
    print(f"Leads created: {summary.leads_created}  Existing leads updated: {summary.leads_existed}")
    if summary.priority:
        print("\nPriority:")
        for key, value in summary.priority.most_common():
            print(f"  {key}: {value}")
    if summary.errors:
        print("\nErrors:")
        for err in summary.errors:
            print(f"  - {err}")
    return 1 if summary.failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
