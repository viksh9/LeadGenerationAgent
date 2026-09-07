#!/usr/bin/env python3
"""Build REAL company-level leads from collected raw job records.

This is the production aggregation step of the pipeline:
  collected raw job records (REAL) -> company aggregation -> REAL company leads.

It fabricates nothing. If no real job data has been collected yet, it creates no
leads (the dashboard then shows the honest empty state).

Usage:
    python scripts/build_company_leads.py
    python scripts/build_company_leads.py --provenance synthetic   # rebuild demo
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
from database.models import DataProvenance  # noqa: E402
from database.session import create_session_factory, get_engine, init_db  # noqa: E402
from intelligence.company_pipeline import rebuild_company_leads  # noqa: E402

logger = logging.getLogger("build_company_leads")


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    parser = argparse.ArgumentParser(description="Aggregate raw job records into company-level leads.")
    parser.add_argument("--provenance", choices=["real", "synthetic"], default="real")
    args = parser.parse_args(argv)

    provenance = DataProvenance.REAL if args.provenance == "real" else DataProvenance.SYNTHETIC
    settings = get_settings()
    engine = get_engine(settings.database_url)
    init_db(engine)
    with create_session_factory(engine)() as session:
        summary = rebuild_company_leads(session, provenance=provenance)

    print(f"Company aggregation ({summary.provenance}):")
    print(f"  raw job records: {summary.jobs}")
    print(f"  companies -> leads: {summary.companies} (created {summary.created}, updated {summary.updated})")
    if summary.jobs == 0:
        print("  No real job data collected yet — no company leads created (honest empty state).")
    if summary.errors:
        print(f"  errors: {len(summary.errors)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
