"""JobCollectionService — run a collector and persist raw records.

Source-agnostic: it takes any BaseCollector and a list of FetchRequests, persists
new RawSourceRecords (deduping by external_id then content_hash), refreshes
last_seen_at on known records, and reports a summary. No scoring/normalization.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Iterable

from sqlalchemy.orm import Session

from collectors.base import BaseCollector, FetchRequest
from collectors.raw_record import RawRecordDraft
from database.models import utcnow
from database.raw_repository import create_raw_record_from_draft, find_by_content_hash, find_by_external_id

logger = logging.getLogger("collectors")


@dataclass
class CollectionSummary:
    source_id: str
    requests: int = 0
    fetched: int = 0
    accepted: int = 0
    skipped_duplicates: int = 0
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    duration_seconds: float = 0.0


class JobCollectionService:
    def __init__(self, session: Session) -> None:
        self.session = session

    def _existing(self, draft: RawRecordDraft):
        if draft.external_id:
            found = find_by_external_id(self.session, draft.source_id, draft.external_id)
            if found is not None:
                return found
        if draft.content_hash:
            return find_by_content_hash(self.session, draft.content_hash)
        return None

    def collect(
        self,
        collector: BaseCollector,
        requests: Iterable[FetchRequest],
        *,
        dry_run: bool = False,
    ) -> CollectionSummary:
        summary = CollectionSummary(source_id=collector.source_id)
        for request in requests:
            summary.requests += 1
            try:
                result = collector.fetch(request)
            except Exception as exc:  # noqa: BLE001 - record, keep going
                summary.errors.append(f"{request.query!r}: {exc}")
                logger.error("collect_request_failed source_id=%s query=%r error=%s", collector.source_id, request.query, exc)
                continue
            summary.fetched += result.records_count
            summary.warnings.extend(result.warnings)
            summary.errors.extend(result.errors)
            summary.duration_seconds += result.duration_seconds or 0.0

            for draft in result.records:
                existing = self._existing(draft)
                if existing is not None:
                    if not dry_run:
                        existing.last_seen_at = utcnow()
                        existing.updated_at = draft.updated_at or existing.updated_at
                        self.session.commit()
                    summary.skipped_duplicates += 1
                    continue
                if not dry_run:
                    record = create_raw_record_from_draft(self.session, draft)
                    record.last_seen_at = record.collected_at
                    self.session.commit()
                summary.accepted += 1

        logger.info(
            "collection_completed source_id=%s requests=%s fetched=%s accepted=%s duplicates=%s",
            collector.source_id, summary.requests, summary.fetched, summary.accepted, summary.skipped_duplicates,
        )
        return summary
