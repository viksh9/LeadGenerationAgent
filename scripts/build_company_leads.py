#!/usr/bin/env python3
"""Build REAL company-level leads from collected raw job records.

This is the production aggregation step of the pipeline:
  collected raw job records (REAL) -> company aggregation -> REAL company leads.

It fabricates nothing. If no real job data has been collected yet, it creates no
leads (the dashboard then shows the honest empty state). This is a real-data-only
runner: it always produces REAL leads from already-collected REAL job records.

Usage:
    python scripts/build_company_leads.py
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
from ingestion.job_pipeline import run_company_pipeline  # noqa: E402

logger = logging.getLogger("build_company_leads")


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    parser = argparse.ArgumentParser(description="Aggregate REAL raw job records into company-level leads.")
    parser.parse_args(argv)

    provenance = DataProvenance.REAL
    settings = get_settings()
    engine = get_engine(settings.database_url)
    init_db(engine)
    with create_session_factory(engine)() as session:
        result = run_company_pipeline(session, provenance=provenance)

    dedup, companies = result.dedup, result.companies
    print(f"Company pipeline ({companies.provenance}): raw -> canonical jobs -> company leads")
    print(f"  raw jobs normalized: {dedup.input_jobs}")
    print(f"  canonical job records: {dedup.canonical_created} (duplicates folded: {dedup.duplicates})")
    print(f"  companies -> leads: {companies.companies} (created {companies.created}, updated {companies.updated})")
    if dedup.input_jobs == 0:
        print("  No real job data collected yet — no company leads created (honest empty state).")
    if companies.errors:
        print(f"  errors: {len(companies.errors)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
