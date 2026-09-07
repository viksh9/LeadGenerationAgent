"""Orchestrator: raw business records -> BusinessSignals -> OpportunityCandidates.

    raw_source_records (NEWS_ARTICLE)
        -> BusinessSignalNormalizationService (classify, value, dates, confidence)
        -> BusinessSignalDeduplicationService  -> BusinessSignal + SignalSourceReference[]
        -> CompanySignalAggregator (+ job intelligence) -> OpportunityCandidate

Real and synthetic are processed independently.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from database.models import DataProvenance, RawSourceRecord, RecordType
from intelligence.business_signal_service import (
    BusinessSignalDeduplicationService,
    BusinessSignalNormalizationService,
)
from intelligence.company_signal_aggregator import CandidateRunSummary, build_opportunity_candidates

logger = logging.getLogger("ingestion")


@dataclass
class BusinessPipelineSummary:
    provenance: str
    signals_created: int
    supporting_added: int
    candidates: CandidateRunSummary


def build_business_signals(session: Session, *, provenance: DataProvenance = DataProvenance.REAL,
                           now: Optional[datetime] = None):
    now = now or datetime.now(timezone.utc).replace(tzinfo=None)
    is_synth = provenance is DataProvenance.SYNTHETIC
    stmt = (
        select(RawSourceRecord)
        .where(RawSourceRecord.record_type == RecordType.NEWS_ARTICLE)
        .where(RawSourceRecord.is_synthetic.is_(is_synth))
    )
    normalizer = BusinessSignalNormalizationService()
    normalized = [normalizer.normalize(r, now=now) for r in session.scalars(stmt)]
    return BusinessSignalDeduplicationService(session).ingest(normalized, provenance=provenance, now=now)


def run_business_pipeline(session: Session, *, provenance: DataProvenance = DataProvenance.REAL,
                          now: Optional[datetime] = None) -> BusinessPipelineSummary:
    now = now or datetime.now(timezone.utc).replace(tzinfo=None)
    dedup = build_business_signals(session, provenance=provenance, now=now)
    candidates = build_opportunity_candidates(session, provenance=provenance, now=now)
    logger.info("business_pipeline provenance=%s signals=%s candidates=%s",
                provenance.value, dedup.created, candidates.candidates)
    return BusinessPipelineSummary(
        provenance=provenance.value, signals_created=dedup.created,
        supporting_added=dedup.supporting_added, candidates=candidates,
    )
