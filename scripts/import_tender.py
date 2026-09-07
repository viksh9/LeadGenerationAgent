#!/usr/bin/env python3
"""Manual tender import — ingest REAL tenders from a permitted source into the pipeline.

For portals with no permitted public API (e.g. CPPP/GeM), an operator can export
tender data they obtained through a permitted method into a JSON file and import it
here. This is the MANUAL_SOURCE_REQUIRED path — it ingests only the operator-provided
REAL data (provenance REAL); it fabricates nothing.

Input JSON: a list of tender objects. Required: source_id, external_id (or id),
title. Optional: description, organization_name, department, organization_type,
location, published_at, issue_date, closing_date, award_date, status,
estimated_value, currency, category, scope_summary, source_url.

    python scripts/import_tender.py tenders.json
    python scripts/import_tender.py tenders.json --dry-run

Absent fields stay NULL/UNKNOWN — never inferred.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from collectors.raw_record import RawRecordDraft  # noqa: E402
from config import get_settings  # noqa: E402
from database.models import DataProvenance  # noqa: E402
from database.raw_repository import create_raw_record_from_draft  # noqa: E402
from database.session import create_session_factory, get_engine, init_db  # noqa: E402
from ingestion.business_pipeline import run_business_pipeline  # noqa: E402
from ingestion.tender_pipeline import run_tender_pipeline  # noqa: E402

logger = logging.getLogger("import_tender")
_TENDER_PAYLOAD_KEYS = (
    "closing_date", "issue_date", "award_date", "status", "tender_status",
    "estimated_value", "currency", "estimated_value_text", "department",
    "organization_type", "organization_name", "category", "scope_summary",
    "eligibility_summary",
)


def _draft(obj: dict) -> RawRecordDraft:
    ext = obj.get("external_id") or obj.get("id")
    if not obj.get("source_id") or not ext or not obj.get("title"):
        raise ValueError("each tender needs source_id, external_id/id, and title")
    payload = {k: obj[k] for k in _TENDER_PAYLOAD_KEYS if obj.get(k) is not None}
    return RawRecordDraft(
        source_id=str(obj["source_id"]), external_id=str(ext), record_type="TENDER",
        source_url=obj.get("source_url"), title=obj["title"],
        description=obj.get("description"),
        company_name=obj.get("organization_name"), location=obj.get("location"),
        industry=obj.get("category"),
        published_at=obj.get("published_at") or obj.get("publication_date"),
        raw_payload=payload, is_synthetic=False,
    )


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    parser = argparse.ArgumentParser(description="Import REAL tenders from a permitted source (JSON).")
    parser.add_argument("file", type=Path, help="Path to a JSON array of tender objects.")
    parser.add_argument("--dry-run", action="store_true", help="Validate + report; persist nothing.")
    args = parser.parse_args(argv)

    data = json.loads(args.file.read_text(encoding="utf-8"))
    if not isinstance(data, list):
        print("Input must be a JSON array of tender objects."); return 1

    drafts, errors = [], []
    for i, obj in enumerate(data):
        try:
            drafts.append(_draft(obj))
        except Exception as exc:  # noqa: BLE001 - one bad record must not abort the batch
            errors.append(f"record {i}: {exc}")
    print(f"Parsed {len(drafts)} valid tender(s); {len(errors)} rejected.")
    for e in errors[:10]:
        print(f"  reject: {e}")
    if args.dry_run:
        print("Dry run — nothing persisted.")
        return 0
    if not drafts:
        print("No valid tenders to import."); return 1

    settings = get_settings()
    engine = get_engine(settings.database_url)
    init_db(engine)
    with create_session_factory(engine)() as session:
        for d in drafts:
            create_raw_record_from_draft(session, d)
        session.commit()
        bp = run_business_pipeline(session, provenance=DataProvenance.REAL)
        tp = run_tender_pipeline(session, provenance=DataProvenance.REAL)
    print(f"Imported: business_signals_created={bp.signals_created} "
          f"tenders_created={tp.created} tenders_updated={tp.updated} errors={len(tp.errors)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
