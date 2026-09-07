"""Consolidated ingestion audit — ACTUAL counts from one real ingestion run.

Assembles the operational metrics required by the real-data ingestion spec from
the genuine return values of the collection + pipeline stages plus direct DB
counts (never fabricated): raw fetched/persisted/duplicates, canonical jobs,
company-level hiring signals, opportunities, and leads created/updated.

"Signals" and "opportunities" here are counted from the REAL company-level leads
that actually carry them — they are evidence-backed aggregates, not estimates
presented as facts.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from database.models import DataProvenance, JobRecord, Lead


@dataclass
class IngestionReport:
    source_id: str
    provenance: str
    # Collection stage (actual)
    requests: int = 0
    records_fetched: int = 0
    records_persisted: int = 0        # new raw records
    duplicates: int = 0
    warnings: int = 0
    errors: int = 0
    # Normalization + dedup (actual)
    normalized_input: int = 0
    canonical_jobs_created: int = 0
    canonical_jobs_updated: int = 0
    # Aggregation (actual)
    companies: int = 0
    leads_created: int = 0
    leads_updated: int = 0
    # Evidence-backed aggregates (counted from real leads)
    companies_with_hiring_signal: int = 0
    opportunities: int = 0
    # DB totals after the run (real-only)
    total_canonical_jobs: int = 0
    total_leads: int = 0
    duration_seconds: float = 0.0

    def as_dict(self) -> dict:
        return asdict(self)


def _count(session: Session, model, *where) -> int:
    stmt = select(func.count()).select_from(model)
    for clause in where:
        stmt = stmt.where(clause)
    return int(session.scalar(stmt) or 0)


def build_ingestion_report(
    session: Session,
    *,
    source_id: str,
    collection_summary,
    pipeline_summary,
    provenance: DataProvenance = DataProvenance.REAL,
    duration_seconds: float = 0.0,
) -> IngestionReport:
    """Build the consolidated report from real stage outputs + DB counts."""
    dedup = pipeline_summary.dedup
    companies = pipeline_summary.companies

    real_leads = session.execute(
        select(Lead).where(Lead.data_provenance == provenance)
    ).scalars().all()
    with_signal = sum(1 for l in real_leads if (l.company_signals or []))
    with_opportunity = sum(
        1 for l in real_leads
        if l.opportunity_summary or l.recommended_action
    )

    return IngestionReport(
        source_id=source_id,
        provenance=provenance.value,
        requests=collection_summary.requests,
        records_fetched=collection_summary.fetched,
        records_persisted=collection_summary.accepted,
        duplicates=collection_summary.skipped_duplicates,
        warnings=len(collection_summary.warnings),
        errors=len(collection_summary.errors),
        normalized_input=dedup.input_jobs,
        canonical_jobs_created=dedup.canonical_created,
        canonical_jobs_updated=dedup.canonical_updated,
        companies=companies.companies,
        leads_created=companies.created,
        leads_updated=companies.updated,
        companies_with_hiring_signal=with_signal,
        opportunities=with_opportunity,
        total_canonical_jobs=_count(session, JobRecord, JobRecord.data_provenance == provenance),
        total_leads=len(real_leads),
        duration_seconds=round(duration_seconds, 2),
    )


def format_ingestion_report(report: IngestionReport, *, country_label: str = "India") -> str:
    """Human-readable §27-style summary of an ingestion run (actual counts)."""
    r = report
    return "\n".join([
        f"Source: {r.source_id}",
        f"Country: {country_label}",
        f"Provenance: {r.provenance}",
        f"Requests: {r.requests}",
        f"Raw records received: {r.records_fetched}",
        f"Raw records persisted (new): {r.records_persisted}",
        f"Duplicates skipped: {r.duplicates}",
        f"Canonical jobs created: {r.canonical_jobs_created}",
        f"Canonical jobs updated: {r.canonical_jobs_updated}",
        f"Companies aggregated: {r.companies}",
        f"Leads created: {r.leads_created}",
        f"Leads updated: {r.leads_updated}",
        f"Companies with hiring signal: {r.companies_with_hiring_signal}",
        f"Opportunities (evidence-backed): {r.opportunities}",
        f"DB totals (REAL): canonical_jobs={r.total_canonical_jobs}, leads={r.total_leads}",
        f"Warnings: {r.warnings} | Errors: {r.errors}",
        f"Duration: {r.duration_seconds}s",
    ])
