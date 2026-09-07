"""Ingestion service: run a collector and persist its raw records.

Deduplicates against the raw layer (by content hash) so re-collecting the same
postings does not create duplicate rows. This is the internal bridge between
collectors and `RawSourceRecord`; it performs no scoring/signal logic.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from sqlalchemy.orm import Session

from collectors.base import BaseCollector, FetchRequest
from database.raw_repository import create_raw_record_from_draft, find_by_content_hash

logger = logging.getLogger("collectors")


@dataclass
class IngestSummary:
    source_id: str
    fetched: int = 0
    created: int = 0
    skipped_duplicates: int = 0
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


def ingest_source(
    collector: BaseCollector,
    session: Session,
    request: FetchRequest | None = None,
) -> IngestSummary:
    """Fetch one batch from `collector` and persist new raw records.

    Duplicate detection uses the deterministic content hash; existing records are
    skipped (not updated) at the raw layer.
    """
    summary = IngestSummary(source_id=collector.source_id)
    result = collector.fetch(request)
    summary.fetched = result.records_count
    summary.warnings.extend(result.warnings)
    summary.errors.extend(result.errors)

    for draft in result.records:
        if draft.content_hash and find_by_content_hash(session, draft.content_hash) is not None:
            summary.skipped_duplicates += 1
            continue
        create_raw_record_from_draft(session, draft)
        summary.created += 1

    logger.info(
        "ingest_completed source_id=%s fetched=%s created=%s skipped=%s",
        collector.source_id, summary.fetched, summary.created, summary.skipped_duplicates,
    )
    return summary
