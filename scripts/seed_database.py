#!/usr/bin/env python3
"""Seed the local development database with SYNTHETIC leads.

All data produced by this script is synthetic and for development/testing only.
Each record is run through the real LeadAnalysisPipeline, so priorities, signals,
opportunities, POC roles and pitches are computed by the engine (never hard-coded).

Usage:
    python scripts/seed_database.py                 # seed all synthetic leads
    python scripts/seed_database.py --count 10      # seed 10 (variety preserved)
    python scripts/seed_database.py --count 50      # seed 50 (generates variants)
    python scripts/seed_database.py --reset --yes   # wipe dev leads, then seed
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from pydantic import ValidationError as PydanticValidationError  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from api.schemas import LeadAnalyzeRequest  # noqa: E402
from config import get_settings  # noqa: E402
from database.models import Lead  # noqa: E402
from database.session import create_session_factory, get_engine, init_db  # noqa: E402
from intelligence.lead_pipeline import LeadAnalysisPipeline  # noqa: E402

logger = logging.getLogger("seed")

DEFAULT_SAMPLE = ROOT / "data" / "sample_leads.json"
SAFE_ENVIRONMENTS = {"development", "test", "local"}


@dataclass
class SeedSummary:
    """Accumulated result of a seed run."""

    total: int = 0
    created: int = 0
    skipped: int = 0
    failed: int = 0
    priority: Counter = field(default_factory=Counter)
    opportunity: Counter = field(default_factory=Counter)
    industry: Counter = field(default_factory=Counter)
    signal: Counter = field(default_factory=Counter)
    errors: list[str] = field(default_factory=list)


# --------------------------------------------------------------------------- #
# Loading / selection / validation
# --------------------------------------------------------------------------- #
def load_sample_leads(path: Path = DEFAULT_SAMPLE) -> list[dict]:
    """Load the synthetic sample leads JSON (a list of dict records)."""
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(data, list):
        raise ValueError("sample leads file must contain a JSON array")
    return data


def select_records(records: list[dict], count: int | None) -> list[dict]:
    """Pick `count` records, preserving variety.

    - count is None -> all records.
    - count <= len -> an even spread across the list (keeps industry/scenario mix).
    - count > len  -> all records plus distinct synthetic variants (never exact
      duplicates: company name + signal title are suffixed).
    """
    if count is None or count >= len(records):
        if count is None or count == len(records):
            return list(records)
        out = list(records)
        i = 0
        while len(out) < count:
            base = records[i % len(records)]
            variant = dict(base)
            pass_no = len(out) // len(records) + 1
            variant["company_name"] = f'{base["company_name"]} {pass_no + 1}'
            variant["signal_title"] = f'{base["signal_title"]} (variant {pass_no})'
            out.append(variant)
            i += 1
        return out[:count]
    step = len(records) / count
    return [records[int(i * step)] for i in range(count)]


def to_analyze_request(record: dict, reference: datetime) -> LeadAnalyzeRequest:
    """Build a validated LeadAnalyzeRequest, converting relative age to a date.

    Raises pydantic ValidationError for invalid records (§22 validation).
    """
    data = {k: v for k, v in record.items() if k != "signal_age_days"}
    age = record.get("signal_age_days")
    if age is not None:
        data["signal_date"] = reference - timedelta(days=int(age))
    return LeadAnalyzeRequest(**data)


# --------------------------------------------------------------------------- #
# Seeding / reset
# --------------------------------------------------------------------------- #
def seed(
    session: Session,
    records: list[dict],
    *,
    reference: datetime | None = None,
    pipeline: LeadAnalysisPipeline | None = None,
) -> SeedSummary:
    """Run each record through the analysis pipeline and persist it.

    Duplicate (company_name, signal_title, source_url) records are updated in
    place by the pipeline rather than re-created — counted as skipped.
    """
    reference = reference or datetime.now(timezone.utc)
    pipeline = pipeline or LeadAnalysisPipeline()
    summary = SeedSummary(total=len(records))

    for record in records:
        company = record.get("company_name", "<unknown>")
        try:
            payload = to_analyze_request(record, reference)
        except PydanticValidationError as exc:
            summary.failed += 1
            summary.errors.append(f"{company}: invalid record ({exc.error_count()} errors)")
            logger.warning("seed_validation_failed company=%s", company)
            continue

        try:
            result = pipeline.analyze(payload, session=session, persist=True)
        except Exception as exc:  # noqa: BLE001 - report per-record, don't abort the run
            summary.failed += 1
            summary.errors.append(f"{company}: analysis failed ({exc})")
            logger.exception("seed_analysis_failed company=%s", company)
            continue

        if result.already_existed:
            summary.skipped += 1
        else:
            summary.created += 1
        summary.priority[result.priority.value] += 1
        summary.opportunity[result.opportunity_analysis.opportunity_type.value] += 1
        summary.industry[record.get("industry") or "Unknown"] += 1
        primary_signal = result.signal_analysis.signal_types[0].value if result.signal_analysis.signal_types else "OTHER"
        summary.signal[primary_signal] += 1

    return summary


def assert_reset_allowed() -> None:
    """Refuse destructive reset outside a development/test/local environment."""
    env = (get_settings().environment or "").lower()
    if env not in SAFE_ENVIRONMENTS:
        raise SystemExit(
            f"Refusing to reset: APP_ENV='{env or '(unset)'}' is not one of "
            f"{sorted(SAFE_ENVIRONMENTS)}. Reset only runs against local development data."
        )


def reset_leads(session: Session) -> int:
    """Delete all leads from the (development) database. Returns rows removed."""
    deleted = session.query(Lead).delete()
    session.commit()
    return deleted


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #
def _print_summary(summary: SeedSummary) -> None:
    print("\nSeed summary")
    print(f"  Total processed: {summary.total}")
    print(f"  Created:         {summary.created}")
    print(f"  Skipped (dups):  {summary.skipped}")
    print(f"  Failed:          {summary.failed}")

    def _dist(title: str, counter: Counter) -> None:
        print(f"\n{title}:")
        for key, value in counter.most_common():
            print(f"  {key}: {value}")

    _dist("Priority", summary.priority)
    _dist("Opportunity", summary.opportunity)
    _dist("Industry", summary.industry)
    _dist("Signal", summary.signal)
    if summary.errors:
        print("\nErrors:")
        for err in summary.errors:
            print(f"  - {err}")


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    parser = argparse.ArgumentParser(description="Seed the local dev database with synthetic leads.")
    parser.add_argument("--count", type=int, default=None, help="Number of synthetic leads to seed.")
    parser.add_argument("--reset", action="store_true", help="Delete existing dev leads before seeding.")
    parser.add_argument("--yes", action="store_true", help="Skip the reset confirmation prompt.")
    parser.add_argument("--sample", type=Path, default=DEFAULT_SAMPLE, help="Path to the sample leads JSON.")
    parser.add_argument("--reference-date", type=str, default=None, help="YYYY-MM-DD reference for signal dates.")
    args = parser.parse_args(argv)

    settings = get_settings()
    reference = (
        datetime.strptime(args.reference_date, "%Y-%m-%d").replace(tzinfo=timezone.utc)
        if args.reference_date
        else datetime.now(timezone.utc)
    )

    engine = get_engine(settings.database_url)
    init_db(engine)
    session_factory = create_session_factory(engine)

    print("Seeding LeadGenerationAgent (synthetic development data)…")
    print(f"  Environment: {settings.environment}")
    print(f"  Database:    {settings.database_url}")

    with session_factory() as session:
        if args.reset:
            assert_reset_allowed()
            if not args.yes:
                confirm = ""
                try:
                    confirm = input("This deletes ALL local dev leads. Type 'yes' to continue: ").strip().lower()
                except EOFError:
                    confirm = ""
                if confirm != "yes":
                    print("Reset cancelled.")
                    return 1
            removed = reset_leads(session)
            print(f"  Reset: removed {removed} existing leads.")

        records = select_records(load_sample_leads(args.sample), args.count)
        print(f"Loaded: {len(records)} synthetic leads")
        summary = seed(session, records, reference=reference)

    _print_summary(summary)
    return 1 if summary.failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
