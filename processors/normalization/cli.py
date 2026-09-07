"""Normalization CLI (read-only).

    python -m processors.normalization.cli --source adzuna --limit 20 --dry-run

Loads raw records from the local database, normalizes them, and shows examples +
a warning summary. It NEVER alters source records (normalization is in-memory).
"""

from __future__ import annotations

import argparse
import logging
from datetime import datetime, timezone


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    parser = argparse.ArgumentParser(description="Normalize raw job records (read-only).")
    parser.add_argument("--source", default=None, help="filter by source_id")
    parser.add_argument("--limit", type=int, default=20)
    parser.add_argument("--dry-run", action="store_true", help="display only; never writes (default behaviour)")
    args = parser.parse_args(argv)

    from config import get_settings
    from database.raw_repository import list_raw_records
    from database.session import create_session_factory, get_engine, init_db
    from processors.normalization.adapters import normalize_raw
    from processors.normalization.normalizer import BatchSummary

    settings = get_settings()
    engine = get_engine(settings.database_url)
    init_db(engine)
    now = datetime.now(timezone.utc).replace(tzinfo=None)

    with create_session_factory(engine)() as session:
        raws = list_raw_records(session, source_id=args.source, limit=args.limit)
        summary = BatchSummary(total=len(raws))
        examples = []
        for raw in raws:
            try:
                nr = normalize_raw(raw, now=now)
            except Exception as exc:  # noqa: BLE001
                summary.failed += 1
                summary.errors.append(str(exc))
                continue
            summary.normalized += 1
            if nr.normalization_warnings:
                summary.warnings += 1
            examples.append(nr)

    print("Normalization (read-only, no source records altered)")
    print("---------------------------------------------------\n")
    print(f"Source: {args.source or 'ALL'} | records: {summary.total}\n")
    for nr in examples[:10]:
        print(f"  [{nr.data_provenance.value}] {nr.original_job_title or '(no title)'}")
        print(f"      -> title={nr.normalized_job_title} | role={nr.role_taxonomy.value} | seniority={nr.seniority_level.value}")
        print(f"      -> city={nr.normalized_city} state={nr.normalized_state} remote={nr.remote_type.value}")
        print(f"      -> tech={nr.normalized_technologies} | it_relevance={nr.it_relevance.value} | conf={nr.normalization_confidence}")
        if nr.normalization_warnings:
            print(f"      -> warnings: {nr.normalization_warnings}")
    print(f"\nSummary: total={summary.total} normalized={summary.normalized} "
          f"with_warnings={summary.warnings} failed={summary.failed}")
    if args.dry_run:
        print("(dry-run — nothing persisted; normalization is always in-memory)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
