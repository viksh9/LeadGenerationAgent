"""Process raw source records into analyzed Leads via the intelligence pipeline."""

from __future__ import annotations

import logging
from collections import Counter
from dataclasses import dataclass, field
from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from database.models import RawSourceRecord, RawStatus
from ingestion.normalizer import normalize_raw_record
from intelligence.lead_pipeline import LeadAnalysisPipeline

logger = logging.getLogger("ingestion")


@dataclass
class ProcessResult:
    raw_id: int
    status: str  # "processed" | "invalid" | "failed"
    lead_id: Optional[int] = None
    lead_existed: bool = False
    priority: Optional[str] = None
    reason: Optional[str] = None


@dataclass
class RunSummary:
    total: int = 0
    processed: int = 0
    invalid: int = 0
    failed: int = 0
    leads_created: int = 0
    leads_existed: int = 0
    priority: Counter = field(default_factory=Counter)
    errors: list[str] = field(default_factory=list)


def process_raw_record(
    session: Session,
    raw: RawSourceRecord,
    pipeline: LeadAnalysisPipeline,
) -> ProcessResult:
    """Normalize one raw record, run the pipeline, persist and link the Lead."""
    request = normalize_raw_record(raw)
    if request is None:
        raw.raw_status = RawStatus.INVALID
        session.commit()
        return ProcessResult(raw.id, "invalid", reason="record could not be normalized")

    # Persist the normalized extraction back onto the raw record.
    raw.technologies = request.technologies
    raw.roles = request.hiring_roles
    raw.raw_status = RawStatus.NORMALIZED

    try:
        result = pipeline.analyze(request, session=session, persist=True)
    except Exception as exc:  # noqa: BLE001 - one bad record must not abort a batch
        raw.raw_status = RawStatus.INVALID
        session.commit()
        logger.exception("ingestion_failed raw_id=%s", raw.id)
        return ProcessResult(raw.id, "failed", reason=str(exc))

    raw.lead_id = result.lead_id
    raw.raw_status = RawStatus.PROCESSED
    session.commit()
    logger.info(
        "ingestion_processed raw_id=%s lead_id=%s existed=%s priority=%s",
        raw.id, result.lead_id, result.already_existed, result.priority.value,
    )
    return ProcessResult(
        raw.id,
        "processed",
        lead_id=result.lead_id,
        lead_existed=result.already_existed,
        priority=result.priority.value,
    )


def process_pending(
    session: Session,
    *,
    limit: Optional[int] = None,
    include_synthetic: bool = True,
    pipeline: Optional[LeadAnalysisPipeline] = None,
) -> RunSummary:
    """Process all NEW raw records into Leads. Re-running skips already-processed rows."""
    pipeline = pipeline or LeadAnalysisPipeline()
    stmt = select(RawSourceRecord).where(RawSourceRecord.raw_status == RawStatus.NEW)
    if not include_synthetic:
        stmt = stmt.where(RawSourceRecord.is_synthetic.is_(False))
    stmt = stmt.order_by(RawSourceRecord.collected_at.asc())
    if limit is not None:
        stmt = stmt.limit(limit)

    records = list(session.scalars(stmt).all())
    summary = RunSummary(total=len(records))
    for raw in records:
        result = process_raw_record(session, raw, pipeline)
        if result.status == "processed":
            summary.processed += 1
            if result.lead_existed:
                summary.leads_existed += 1
            else:
                summary.leads_created += 1
            if result.priority:
                summary.priority[result.priority] += 1
        elif result.status == "invalid":
            summary.invalid += 1
        else:
            summary.failed += 1
            if result.reason:
                summary.errors.append(f"raw {result.raw_id}: {result.reason}")
    return summary
