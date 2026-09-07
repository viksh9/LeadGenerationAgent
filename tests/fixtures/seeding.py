"""Test-only seeding helpers.

These utilities build SYNTHETIC leads from ``tests/fixtures/sample_leads.json``
and run them through the real ``LeadAnalysisPipeline`` so tests can exercise the
scoring / opportunity / POC / dedup logic against known-shaped input.

IMPORTANT: this module lives entirely inside the test suite. It is NEVER imported
by application/runtime code and must never write to a production database. Every
record it produces is tagged ``DataProvenance.SYNTHETIC`` and is only ever loaded
into an isolated, per-test database (see ``tests/integration/conftest.py``).
"""

from __future__ import annotations

import json
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path

from sqlalchemy.orm import Session

from api.schemas import LeadAnalyzeRequest
from database.models import DataProvenance, Lead
from intelligence.lead_pipeline import LeadAnalysisPipeline

FIXTURE_DIR = Path(__file__).resolve().parent
SAMPLE_LEADS = FIXTURE_DIR / "sample_leads.json"


@dataclass
class SeedSummary:
    total: int = 0
    created: int = 0
    skipped: int = 0
    failed: int = 0
    priority: Counter = field(default_factory=Counter)
    opportunity: Counter = field(default_factory=Counter)
    industry: Counter = field(default_factory=Counter)
    signal: Counter = field(default_factory=Counter)
    errors: list[str] = field(default_factory=list)


def load_sample_leads(path: Path = SAMPLE_LEADS) -> list[dict]:
    """Load the synthetic sample-lead records (a JSON array of dicts)."""
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(data, list):
        raise ValueError("sample leads file must contain a JSON array")
    return data


def select_records(records: list[dict], count: int | None) -> list[dict]:
    """Pick ``count`` records, preserving variety (mirrors the old CLI helper)."""
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
    """Build a validated request, converting relative ``signal_age_days`` to a date."""
    data = {k: v for k, v in record.items() if k != "signal_age_days"}
    age = record.get("signal_age_days")
    if age is not None:
        data["signal_date"] = reference - timedelta(days=int(age))
    return LeadAnalyzeRequest(**data)


def seed(
    session: Session,
    records: list[dict],
    *,
    reference: datetime | None = None,
    pipeline: LeadAnalysisPipeline | None = None,
) -> SeedSummary:
    """Run each record through the analysis pipeline and persist it as SYNTHETIC."""
    from pydantic import ValidationError as PydanticValidationError

    reference = reference or datetime.now(timezone.utc)
    pipeline = pipeline or LeadAnalysisPipeline()
    summary = SeedSummary(total=len(records))

    for record in records:
        company = record.get("company_name", "<unknown>")
        try:
            payload = to_analyze_request(record, reference)
        except PydanticValidationError:
            summary.failed += 1
            summary.errors.append(f"{company}: invalid record")
            continue

        try:
            result = pipeline.analyze(
                payload, session=session, persist=True, provenance=DataProvenance.SYNTHETIC
            )
        except Exception as exc:  # noqa: BLE001 - report per record, don't abort
            summary.failed += 1
            summary.errors.append(f"{company}: analysis failed ({exc})")
            continue

        if result.already_existed:
            summary.skipped += 1
        else:
            summary.created += 1
        summary.priority[result.priority.value] += 1
        summary.opportunity[result.opportunity_analysis.opportunity_type.value] += 1
        summary.industry[record.get("industry") or "Unknown"] += 1
        primary_signal = (
            result.signal_analysis.signal_types[0].value
            if result.signal_analysis.signal_types else "OTHER"
        )
        summary.signal[primary_signal] += 1

    return summary


def reset_leads(session: Session) -> int:
    """Delete all leads from the (isolated test) database. Returns rows removed."""
    deleted = session.query(Lead).delete()
    session.commit()
    return deleted
