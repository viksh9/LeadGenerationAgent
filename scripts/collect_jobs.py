#!/usr/bin/env python3
"""Collect real IT job postings from Adzuna into the raw ingestion layer.

Requires environment credentials (never committed):
    SOURCE_ADZUNA_APP_ID, SOURCE_ADZUNA_API_KEY  [, SOURCE_ADZUNA_COUNTRY]

Usage:
    python scripts/collect_jobs.py --query "cloud engineer" --pages 2 --per-page 50
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from collectors.adzuna import AdzunaCollector, CollectorError  # noqa: E402
from collectors.base import FetchRequest, HealthStatus  # noqa: E402
from collectors.ingest import ingest_source  # noqa: E402
from collectors.source_registry import get_registry  # noqa: E402
from config import get_settings  # noqa: E402
from database.session import create_session_factory, get_engine, init_db  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    parser = argparse.ArgumentParser(description="Collect IT jobs from Adzuna into raw_source_records.")
    parser.add_argument("--query", default="software engineer", help="Search term (IT role/tech).")
    parser.add_argument("--pages", type=int, default=1, help="Number of pages to fetch.")
    parser.add_argument("--per-page", type=int, default=20, help="Results per page (max 50).")
    args = parser.parse_args(argv)

    source = get_registry().get("adzuna")
    if source is None:
        print("Adzuna source is not in the registry.")
        return 1

    collector = AdzunaCollector(source)
    health = collector.health_check()
    if health.status == HealthStatus.NOT_CONFIGURED:
        print("Adzuna is not configured. Set SOURCE_ADZUNA_APP_ID and SOURCE_ADZUNA_API_KEY.")
        return 1

    settings = get_settings()
    engine = get_engine(settings.database_url)
    init_db(engine)
    session_factory = create_session_factory(engine)

    total_created = total_skipped = total_fetched = 0
    print(f"Collecting Adzuna jobs (query={args.query!r}) into {settings.database_url}")
    with session_factory() as session:
        try:
            for page in range(1, args.pages + 1):
                summary = ingest_source(
                    collector,
                    session,
                    FetchRequest(query=args.query, page=page, limit=args.per_page),
                )
                total_fetched += summary.fetched
                total_created += summary.created
                total_skipped += summary.skipped_duplicates
                for warning in summary.warnings:
                    print(f"  warning: {warning}")
        except CollectorError as exc:
            print(f"Collection failed: {exc}")
            return 1

    print(f"\nFetched: {total_fetched}  Created: {total_created}  Skipped duplicates: {total_skipped}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
