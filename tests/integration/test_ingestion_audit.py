"""Offline test for the consolidated ingestion audit report (real counts)."""

from __future__ import annotations

from collectors.service import CollectionSummary
from database.models import DataProvenance, Lead
from ingestion.ingestion_audit import build_ingestion_report, format_ingestion_report
from ingestion.job_dedup import DedupSummary
from ingestion.job_pipeline import PipelineSummary
from intelligence.company_pipeline import CompanyRunSummary


def _pipeline_summary() -> PipelineSummary:
    dedup = DedupSummary(provenance="REAL", input_jobs=40, canonical_created=30,
                         canonical_updated=5, duplicates=10)
    companies = CompanyRunSummary(provenance="REAL", jobs=30, companies=12, created=8, updated=4)
    return PipelineSummary(provenance="REAL", dedup=dedup, companies=companies)


def test_ingestion_report_uses_actual_counts(seed_session):
    # Two real leads: one with a hiring signal + opportunity, one bare.
    seed_session.add_all([
        Lead(company_name="Acme", data_provenance=DataProvenance.REAL,
             source_url="https://x/1", source_count=3,
             company_signals=["LARGE_TECH_HIRING"], opportunity_summary="Scaling backend team"),
        Lead(company_name="Beta", data_provenance=DataProvenance.REAL,
             source_url="https://x/2", source_count=1),
    ])
    seed_session.commit()

    collection = CollectionSummary(source_id="adzuna", requests=3, fetched=59,
                                   accepted=27, skipped_duplicates=32)
    report = build_ingestion_report(
        seed_session, source_id="adzuna", collection_summary=collection,
        pipeline_summary=_pipeline_summary(), provenance=DataProvenance.REAL,
        duration_seconds=6.1,
    )

    assert report.requests == 3
    assert report.records_fetched == 59
    assert report.records_persisted == 27
    assert report.duplicates == 32
    assert report.canonical_jobs_created == 30
    assert report.leads_created == 8 and report.leads_updated == 4
    assert report.companies_with_hiring_signal == 1     # only Acme has a signal
    assert report.opportunities == 1                    # only Acme has an opportunity
    assert report.total_leads == 2
    assert report.provenance == "REAL"

    text = format_ingestion_report(report)
    assert "Source: adzuna" in text
    assert "Raw records persisted (new): 27" in text


def test_report_zero_when_nothing_collected(seed_session):
    collection = CollectionSummary(source_id="adzuna")
    dedup = DedupSummary(provenance="REAL")
    companies = CompanyRunSummary(provenance="REAL")
    report = build_ingestion_report(
        seed_session, source_id="adzuna", collection_summary=collection,
        pipeline_summary=PipelineSummary(provenance="REAL", dedup=dedup, companies=companies),
    )
    assert report.records_fetched == 0
    assert report.leads_created == 0
    assert report.total_leads == 0
