#!/usr/bin/env python3
"""Collect REAL Indian IT jobs from the Adzuna API and build company-level leads.

End-to-end real-data runner:
  Adzuna API → RawSourceRecord (REAL) → normalize → dedup → company leads (REAL).

Safety / honesty:
  * Requires ADZUNA_APP_ID / ADZUNA_APP_KEY in the environment. Without them it
    prints NOT_CONFIGURED and exits — it never fabricates data.
  * Runs a live health check first and refuses to proceed unless the API actually
    answers, so we never claim a connection that isn't real.
  * Everything persisted is provenance REAL with a source_url back to Adzuna.

Usage:
    python scripts/collect_adzuna.py                      # use configured terms/locations
    python scripts/collect_adzuna.py --query "python developer" --location Bengaluru
    python scripts/collect_adzuna.py --max-pages 2 --per-page 20 --dry-run
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _load_dotenv(path: Path) -> None:
    """Minimal .env loader (no dependency). Existing env vars win; secrets are
    never printed. Only sets simple KEY=VALUE lines."""
    if not path.is_file():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key, value = key.strip(), value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


_load_dotenv(ROOT / ".env")

from collectors.base import FetchRequest  # noqa: E402
from collectors.jobs.adzuna import AdzunaJobCollector  # noqa: E402
from collectors.jobs.config import load_adzuna_config  # noqa: E402
from collectors.service import JobCollectionService  # noqa: E402
from collectors.source_registry import get_registry  # noqa: E402
from config import get_settings  # noqa: E402
from database.integrity import audit_database  # noqa: E402
from database.models import DataProvenance  # noqa: E402
from database.session import create_session_factory, get_engine, init_db  # noqa: E402
from ingestion.job_pipeline import run_company_pipeline  # noqa: E402

logger = logging.getLogger("collect_adzuna")

# Exit codes: 0 ok, 2 not configured, 3 health check failed.
EXIT_OK, EXIT_NOT_CONFIGURED, EXIT_UNHEALTHY = 0, 2, 3


def _requests(config, args) -> list[FetchRequest]:
    queries = [args.query] if args.query else list(config.search_terms)
    locations = [args.location] if args.location else (list(config.locations) or [None])
    per_page = args.per_page or config.results_per_page
    reqs: list[FetchRequest] = []
    for q in queries:
        for loc in locations:
            for page in range(1, (args.max_pages or config.max_pages) + 1):
                reqs.append(FetchRequest(query=q, location=loc, page=page, limit=per_page))
    return reqs


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    parser = argparse.ArgumentParser(description="Collect REAL Adzuna IT jobs and build company leads.")
    parser.add_argument("--query", help="Override search term (default: configured ADZUNA_SEARCH_TERMS).")
    parser.add_argument("--location", help="Override location (default: configured ADZUNA_LOCATIONS).")
    parser.add_argument("--max-pages", type=int, help="Pages per query/location (default: config).")
    parser.add_argument("--per-page", type=int, help="Results per page (default: config).")
    parser.add_argument("--dry-run", action="store_true", help="Fetch and report, but persist nothing.")
    parser.add_argument("--skip-aggregate", action="store_true", help="Collect raw records only; skip lead build.")
    args = parser.parse_args(argv)

    config = load_adzuna_config()
    if not config.is_configured:
        print("Adzuna is NOT_CONFIGURED — set ADZUNA_APP_ID and ADZUNA_APP_KEY in the environment "
              "(see .env.example / docs/sources/adzuna.md). No data collected.")
        return EXIT_NOT_CONFIGURED

    source = get_registry().get("adzuna")
    collector = AdzunaJobCollector(source, config=config)

    # 1) Live health check — do not proceed (or claim connectivity) unless real.
    health = collector.health_check()
    print(f"Adzuna health check: {health.status.value} — {health.message or ''}".rstrip())
    if health.status.value not in {"HEALTHY", "CONNECTED"}:
        print("Refusing to proceed: the Adzuna API did not respond healthily. No data collected.")
        return EXIT_UNHEALTHY

    settings = get_settings()
    engine = get_engine(settings.database_url)
    init_db(engine)
    reqs = _requests(config, args)
    print(f"Collecting from Adzuna (country={config.country}): {len(reqs)} request(s) "
          f"across {len({r.query for r in reqs})} term(s) and {len({r.location for r in reqs})} location(s)"
          f"{' [DRY RUN]' if args.dry_run else ''}…")

    with create_session_factory(engine)() as session:
        summary = JobCollectionService(session).collect(collector, reqs, dry_run=args.dry_run)
        print(f"  requests={summary.requests} fetched={summary.fetched} "
              f"new_raw_records={summary.accepted} duplicates={summary.skipped_duplicates} "
              f"errors={len(summary.errors)}")
        for w in summary.warnings[:5]:
            print(f"  warning: {w}")
        for e in summary.errors[:5]:
            print(f"  error: {e}")

        if args.dry_run:
            print("Dry run — nothing persisted.")
            return EXIT_OK

        if not args.skip_aggregate:
            result = run_company_pipeline(session, provenance=DataProvenance.REAL)
            c = result.companies
            print(f"Aggregation (REAL): canonical_jobs={result.dedup.canonical_created} "
                  f"companies→leads={c.companies} (created {c.created}, updated {c.updated})")

        audit = audit_database(session)
        print(f"DB now: {audit.total_records} real business record(s); "
              f"synthetic={audit.synthetic_total}; clean={audit.is_clean}")

    return EXIT_OK


if __name__ == "__main__":
    raise SystemExit(main())
