"""Deduplication CLI.

    python -m processors.deduplication.cli --source adzuna --limit 100 --dry-run

Shows input records, canonical jobs, auto-merged, review candidates, and the
duplicate rate. --dry-run computes without persisting. --review-only lists
pending duplicate candidates awaiting human review.
"""

from __future__ import annotations

import argparse
import logging
from datetime import datetime, timezone


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    parser = argparse.ArgumentParser(description="Cross-source job deduplication.")
    parser.add_argument("--source", default=None, help="filter raw records by source_id")
    parser.add_argument("--limit", type=int, default=100)
    parser.add_argument("--dry-run", action="store_true", help="compute without persisting")
    parser.add_argument("--review-only", action="store_true", help="list pending review candidates and exit")
    parser.add_argument("--provenance", choices=["real", "synthetic"], default="real")
    args = parser.parse_args(argv)

    from config import get_settings
    from database.models import DataProvenance
    from database.raw_repository import list_raw_records
    from database.session import create_session_factory, get_engine, init_db
    from processors.deduplication import JobDeduplicationService
    from processors.deduplication.repository import list_pending_duplicates

    settings = get_settings()
    engine = get_engine(settings.database_url)
    init_db(engine)
    now = datetime.now(timezone.utc).replace(tzinfo=None)

    with create_session_factory(engine)() as session:
        if args.review_only:
            pending = list_pending_duplicates(session, limit=args.limit)
            print(f"Pending duplicate candidates: {len(pending)}\n")
            for c in pending[:20]:
                print(f"  [{c.match_confidence.value} {c.match_score}] {c.record_a.get('title')} <> {c.record_b.get('title')}")
                print(f"      matched={c.matched_fields} differences={c.differences}")
            return 0

        provenance = DataProvenance.REAL if args.provenance == "real" else DataProvenance.SYNTHETIC
        raws = list_raw_records(session, source_id=args.source, limit=args.limit)
        raws = [r for r in raws if r.record_type.value == "JOB_POSTING"]
        summary = JobDeduplicationService(session).deduplicate(
            raws, provenance=provenance, persist=not args.dry_run, now=now,
        )

    print("Cross-Source Job Deduplication")
    print("------------------------------\n")
    print(f"Source: {args.source or 'ALL'}")
    print(f"Input source records:   {summary.input_records}")
    print(f"Canonical jobs:         {summary.canonical_jobs}")
    print(f"Auto-merged duplicates: {summary.auto_merged}")
    print(f"Review candidates:      {summary.review_candidates}")
    print(f"Source references:      {summary.source_references}")
    print(f"Duplicate rate:         {summary.duplicate_rate:.1%}")
    print(f"Dedup version:          {summary.deduplication_version}")
    if args.dry_run:
        print("\n(dry-run — nothing persisted)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
