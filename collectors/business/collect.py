"""Development CLI for business-signal collection.

    python -m collectors.business.collect --query "digital transformation" \
        --country IN --days 7 --max-records 10 --dry-run

Dry-run fetches, parses, classifies, and summarizes without persisting.
"""

from __future__ import annotations

import argparse
import logging
from typing import Optional

from collectors.base import FetchRequest, HealthStatus
from collectors.business.collector import BusinessSignalCollector
from collectors.business.config import load_business_config
from collectors.company.http_client import CareerCollectorError, RestrictedError
from collectors.source_registry import (
    SourceCategory,
    SourceDefinition,
    SourceStatus,
    SourceType,
    get_registry,
)


def _source(args) -> Optional[SourceDefinition]:
    if args.source:
        return get_registry().get(args.source)
    if args.url:
        return SourceDefinition(
            source_id="business_cli",
            name="(cli business feed)",
            category=SourceCategory.NEWS,
            source_type=SourceType.RSS,
            base_url=args.url,
            status=SourceStatus.REQUIRES_REVIEW,
        )
    return None


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    parser = argparse.ArgumentParser(description="Business-signal collector (dev CLI).")
    parser.add_argument("--source", default=None, help="source_id from config/sources.yaml")
    parser.add_argument("--url", default=None, help="ad-hoc feed URL (RSS/Atom)")
    parser.add_argument("--query", default=None)
    parser.add_argument("--country", default="IN")
    parser.add_argument("--days", type=int, default=7)
    parser.add_argument("--max-records", type=int, default=10)
    parser.add_argument("--dry-run", action="store_true", help="fetch + classify + summarize, do not persist")
    args = parser.parse_args(argv)

    source = _source(args)
    if source is None or not source.base_url:
        print("Provide --url <feed> or --source <id> with a configured feed URL.")
        return 1

    config = load_business_config().model_copy(update={"lookback_days": args.days, "max_records": args.max_records})
    collector = BusinessSignalCollector(source, config=config, resolve_hosts=True)

    print("Business-Signal Collector")
    print("-------------------------\n")
    print(f"Source: {source.source_id}\nFeed: {source.base_url}\nCountry: {args.country}\nLookback: {args.days}d\n")

    health = collector.health_check()
    print(f"Health: {health.status.value} — {health.message}")
    if health.status in {HealthStatus.NOT_CONFIGURED, HealthStatus.RESTRICTED}:
        return 1

    try:
        result = collector.fetch(FetchRequest(query=args.query, limit=args.max_records))
    except (CareerCollectorError, RestrictedError) as exc:
        print(f"Collection failed: {exc}")
        return 1

    ctx = result.context
    print(
        f"\nFeed items: {ctx['feed_items']}\nRelevant records: {ctx['records_accepted']}\n"
        f"Filtered (non-IT-business): {ctx['skipped_irrelevant']}\nSkipped (old): {ctx['skipped_old']}\n"
        f"Warnings: {len(result.warnings)}"
    )
    for draft in result.records[:10]:
        st = draft.raw_payload.get("detected_signal_type")
        print(f"  [{st}] {draft.title}")

    if args.dry_run:
        print("\n(dry-run — nothing persisted)")
        return 0

    from collectors.service import JobCollectionService
    from config import get_settings
    from database.session import create_session_factory, get_engine, init_db

    settings = get_settings()
    engine = get_engine(settings.database_url)
    init_db(engine)
    with create_session_factory(engine)() as session:
        summary = JobCollectionService(session).collect(collector, [FetchRequest(query=args.query, limit=args.max_records)])
    print(f"\nPersisted raw records: accepted={summary.accepted} duplicates={summary.skipped_duplicates}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
