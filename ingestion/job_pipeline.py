"""Orchestrator: raw job records -> normalized -> deduplicated JobRecords ->
company-level leads. Ties the collection layer to company intelligence.

    raw_source_records
        -> JobNormalizationService  (location, normalized_role, quality)
        -> JobDeduplicationService  -> JobRecord + JobSourceReference[]
        -> CompanyHiringAggregator  -> Lead

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
from ingestion.job_dedup import DedupSummary, JobDeduplicationService
from ingestion.job_normalization import JobNormalizationService
from intelligence.company_pipeline import CompanyRunSummary, rebuild_company_leads

logger = logging.getLogger("ingestion")


@dataclass
class PipelineSummary:
    provenance: str
    dedup: DedupSummary
    companies: CompanyRunSummary


def build_job_records(
    session: Session,
    *,
    provenance: DataProvenance = DataProvenance.REAL,
    now: Optional[datetime] = None,
) -> DedupSummary:
    """Normalize + deduplicate raw job records into canonical JobRecords."""
    now = now or datetime.now(timezone.utc).replace(tzinfo=None)
    is_synth = provenance is DataProvenance.SYNTHETIC
    stmt = (
        select(RawSourceRecord)
        .where(RawSourceRecord.record_type == RecordType.JOB_POSTING)
        .where(RawSourceRecord.is_synthetic.is_(is_synth))
    )
    normalizer = JobNormalizationService()
    normalized = [normalizer.normalize(r, now=now) for r in session.scalars(stmt)]
    return JobDeduplicationService(session).ingest(normalized, provenance=provenance, now=now)


def run_company_pipeline(
    session: Session,
    *,
    provenance: DataProvenance = DataProvenance.REAL,
    now: Optional[datetime] = None,
) -> PipelineSummary:
    """Full pipeline: raw -> canonical JobRecords -> company-level leads."""
    now = now or datetime.now(timezone.utc).replace(tzinfo=None)
    dedup = build_job_records(session, provenance=provenance, now=now)
    companies = rebuild_company_leads(session, provenance=provenance, now=now, source="canonical")
    logger.info(
        "company_pipeline provenance=%s canonical_jobs=%s companies=%s",
        provenance.value, dedup.canonical_created + dedup.canonical_updated, companies.companies,
    )
    return PipelineSummary(provenance=provenance.value, dedup=dedup, companies=companies)
