#!/usr/bin/env python3
"""Seed the dev database with SYNTHETIC company-level opportunities.

Demonstrates the REAL pipeline end-to-end on clearly-labelled demo data:
  sample_jobs.json -> synthetic raw job records -> company aggregation ->
  SYNTHETIC company leads.

All companies here are fictional (*.example) and every produced lead is tagged
data_provenance = SYNTHETIC, so the production dashboard (REAL-only) never shows
them. Use `scripts/build_company_leads.py` for real collected data.

Usage:
    python scripts/seed_demo_companies.py --reset --yes
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from sqlalchemy import delete  # noqa: E402

from collectors.raw_record import RawRecordDraft  # noqa: E402
from config import get_settings  # noqa: E402
from database.models import DataProvenance, Lead, RawSourceRecord  # noqa: E402
from database.raw_repository import create_raw_record_from_draft  # noqa: E402
from database.session import create_session_factory, get_engine, init_db  # noqa: E402
from intelligence.company_pipeline import rebuild_company_leads  # noqa: E402

logger = logging.getLogger("seed_demo")

DEFAULT_JOBS = ROOT / "data" / "sample_jobs.json"
DEMO_SOURCES = ("demo_jobs", "demo_career")
SAFE_ENVIRONMENTS = {"development", "test", "local"}


def _drafts(path: Path, now: datetime) -> list[RawRecordDraft]:
    data = json.loads(path.read_text(encoding="utf-8"))
    drafts: list[RawRecordDraft] = []
    for company in data.get("companies", []):
        name = company["company_name"]
        domain = company.get("company_domain")
        city = company.get("city")
        industry = company.get("industry")
        location = f"{city}, India" if city else "India"
        for r_idx, role in enumerate(company.get("roles", [])):
            title = role["title"]
            techs = role.get("technologies", [])
            days_ago = role.get("days_ago", 7)
            published = now - timedelta(days=days_ago)
            sources = role.get("sources", ["demo_jobs"])
            for count_i in range(role.get("count", 1)):
                for source_id in sources:
                    ext = f"{source_id}-{r_idx}-{count_i}"
                    drafts.append(RawRecordDraft(
                        source_id=source_id,
                        external_id=ext,
                        source_url=f"https://{domain or 'demo.example'}/jobs/{ext}",
                        published_at=published,
                        record_type="JOB_POSTING",
                        title=title,
                        description=f"{title} at {name}. Technologies: {', '.join(techs)}.",
                        company_name=name,
                        company_domain=domain,
                        location=location,
                        industry=industry,
                        technologies=list(techs),
                        is_synthetic=True,
                    ))
    return drafts


def _reset(session) -> None:
    session.execute(delete(RawSourceRecord).where(RawSourceRecord.source_id.in_(DEMO_SOURCES)))
    session.execute(
        delete(Lead).where(
            Lead.data_provenance == DataProvenance.SYNTHETIC, Lead.it_job_count > 0
        )
    )
    session.commit()


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    parser = argparse.ArgumentParser(description="Seed synthetic company-level demo opportunities.")
    parser.add_argument("--jobs", type=Path, default=DEFAULT_JOBS)
    parser.add_argument("--reset", action="store_true", help="clear prior demo jobs + synthetic company leads first")
    parser.add_argument("--yes", action="store_true", help="confirm --reset without prompting")
    args = parser.parse_args(argv)

    settings = get_settings()
    if settings.environment.lower() not in SAFE_ENVIRONMENTS:
        print(f"Refusing to seed demo data in environment '{settings.environment}'.")
        return 1

    # Deterministic timestamp base is fine for a demo; use wall-clock day.
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    engine = get_engine(settings.database_url)
    init_db(engine)
    with create_session_factory(engine)() as session:
        if args.reset:
            if not args.yes:
                print("Pass --yes with --reset to confirm clearing demo data.")
                return 1
            _reset(session)
        drafts = _drafts(args.jobs, now)
        for draft in drafts:
            create_raw_record_from_draft(session, draft)
        session.commit()
        summary = rebuild_company_leads(session, provenance=DataProvenance.SYNTHETIC, now=now)

    print("Synthetic company demo seeded (data_provenance = SYNTHETIC).")
    print(f"  raw job records inserted: {len(drafts)}")
    print(f"  companies -> leads: {summary.companies} (created {summary.created}, updated {summary.updated})")
    if summary.errors:
        print(f"  errors: {len(summary.errors)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
