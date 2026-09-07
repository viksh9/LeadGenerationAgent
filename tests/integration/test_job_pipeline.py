"""Integration: full pipeline (raw -> canonical -> company leads) + audit."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import httpx

from collectors.base import FetchRequest
from collectors.jobs.adzuna import AdzunaJobCollector
from collectors.jobs.config import AdzunaConfig
from collectors.raw_record import RawRecordDraft
from collectors.service import JobCollectionService
from collectors.source_registry import get_registry
from database.models import CollectionRun, CollectionRunStatus, DataProvenance, Lead
from database.raw_repository import create_raw_record_from_draft
from database.repository import query_leads
from ingestion.job_pipeline import run_company_pipeline
from sqlalchemy import select

NOW = datetime(2026, 9, 5)


def _raw(session, company, title, techs, *, city="Bengaluru", source="adzuna", ext, days_ago=3, synthetic=False):
    return create_raw_record_from_draft(session, RawRecordDraft(
        source_id=source, external_id=ext, source_url=f"https://x/{ext}",
        published_at=NOW - timedelta(days=days_ago), record_type="JOB_POSTING",
        title=title, description=f"{title}. {' '.join(techs)}", company_name=company,
        location=f"{city}, India", industry="Software", technologies=list(techs), is_synthetic=synthetic,
    ))


def test_pipeline_raw_to_company_lead(seed_session):
    for i in range(30):
        _raw(seed_session, "Ravi Technologies Pvt Ltd", f"Java Developer {i}", ["Java", "AWS", "DevOps"], ext=f"j{i}")
    result = run_company_pipeline(seed_session, provenance=DataProvenance.REAL, now=NOW)
    assert result.dedup.canonical_created == 30
    assert result.companies.companies == 1

    leads, total = query_leads(seed_session, provenance=DataProvenance.REAL, page_size=10)
    assert total == 1
    lead = leads[0]
    assert lead.it_job_count == 30
    assert lead.data_provenance is DataProvenance.REAL
    assert lead.evidence and lead.lead_priority.value in {"HOT", "WARM", "NURTURE", "LOW"}


def test_pipeline_cross_source_company_source_count(seed_session):
    _raw(seed_session, "Ravi Technologies", "Java Developer", ["Java"], city="Pune", source="adzuna", ext="a1")
    _raw(seed_session, "Ravi Technologies", "Java Developer", ["Java"], city="Pune", source="company_career", ext="c1")
    run_company_pipeline(seed_session, provenance=DataProvenance.REAL, now=NOW)
    leads, _ = query_leads(seed_session, provenance=DataProvenance.REAL, page_size=10)
    assert leads[0].it_job_count == 1        # one opening
    assert leads[0].source_count == 2        # confirmed by two sources


# --- Collection-run audit -------------------------------------------------- #
def _mock_adzuna(handler):
    http = httpx.Client(transport=httpx.MockTransport(handler))
    config = AdzunaConfig(app_id="i", app_key="k", country="in", requests_per_minute=0)
    return AdzunaJobCollector(get_registry().get("adzuna"), config=config, http=http, sleep=lambda *_: None)


def test_collection_run_recorded(seed_session):
    def handler(request):
        return httpx.Response(200, json={"results": [
            {"id": "1", "title": "Java Developer", "company": {"display_name": "Ravi Technologies"},
             "location": {"display_name": "Bengaluru"}, "redirect_url": "https://x/1",
             "created": "2026-09-03T00:00:00Z", "category": {"label": "IT Jobs"}},
        ], "count": 1})

    collector = _mock_adzuna(handler)
    summary = JobCollectionService(seed_session).collect(collector, [FetchRequest(query="java", limit=5)])
    assert summary.run_id is not None
    run = seed_session.get(CollectionRun, summary.run_id)
    assert run.source_id == "adzuna"
    assert run.status is CollectionRunStatus.COMPLETED
    assert run.records_created == 1
    assert run.completed_at is not None


def test_dry_run_records_no_collection_run(seed_session):
    def handler(request):
        return httpx.Response(200, json={"results": [], "count": 0})

    collector = _mock_adzuna(handler)
    summary = JobCollectionService(seed_session).collect(collector, [FetchRequest(query="java")], dry_run=True)
    assert summary.run_id is None
    assert seed_session.scalar(select(CollectionRun.id)) is None
