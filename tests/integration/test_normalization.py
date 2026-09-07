"""Tests for the raw-to-lead normalization pipeline."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from collectors.raw_record import RawRecordDraft
from database.models import Lead, RawSourceRecord, RawStatus
from database.raw_repository import create_raw_record_from_draft
from ingestion.normalizer import (
    extract_estimated_hiring,
    extract_roles,
    extract_technologies,
    normalize_raw_record,
    source_label,
)
from ingestion.processor import process_pending, process_raw_record
from intelligence.lead_pipeline import LeadAnalysisPipeline

NOW = datetime(2026, 9, 5, tzinfo=timezone.utc)


def _raw(session, **overrides) -> RawSourceRecord:
    base = dict(
        source_id="adzuna",
        external_id="job-1",
        source_url="https://synthetic.example/jobs/1",
        title="Hiring 25 Java Engineers",
        description="Won a project awarded by a bank; hiring 25 Java, Spring Boot and AWS engineers.",
        company_name="ABC Technologies Pvt Ltd",
        record_type="JOB_POSTING",
        published_at=NOW,
        is_synthetic=True,
    )
    base.update(overrides)
    return create_raw_record_from_draft(session, RawRecordDraft(**base))


# -- extraction ---------------------------------------------------------------
def test_extract_technologies_reuses_canonical_aliases():
    techs = extract_technologies("We use Java, Spring Boot, AWS and Kubernetes.")
    assert {"Java", "Spring Boot", "AWS", "Kubernetes"} <= set(techs)


def test_extract_roles_and_hiring():
    text = "Hiring 30 Java Engineers and DevOps Engineers for delivery."
    assert "Java Engineer" in extract_roles(text)
    assert "DevOps Engineer" in extract_roles(text)
    assert extract_estimated_hiring(text) == 30


def test_source_label():
    assert source_label("adzuna") == "Adzuna"
    assert source_label("some_new_source") == "Some New Source"


# -- normalization ------------------------------------------------------------
def test_normalize_maps_and_extracts(seed_session):
    raw = _raw(seed_session)
    req = normalize_raw_record(raw)
    assert req is not None
    assert req.company_name == "ABC Technologies Pvt Ltd"
    assert req.signal_title == "Hiring 25 Java Engineers"
    assert req.signal_date is not None and req.signal_date.date() == NOW.date()
    assert req.source_name == "Adzuna"
    assert "Java" in req.technologies and "AWS" in req.technologies
    assert "Java Engineer" in req.hiring_roles
    assert req.estimated_hiring == 25


def test_normalize_returns_none_without_company(seed_session):
    raw = _raw(seed_session, company_name=None)
    assert normalize_raw_record(raw) is None


# -- processing ---------------------------------------------------------------
def test_process_creates_and_links_lead(seed_session):
    raw = _raw(seed_session)
    pipeline = LeadAnalysisPipeline()
    result = process_raw_record(seed_session, raw, pipeline)

    assert result.status == "processed"
    assert result.lead_id is not None
    assert result.priority in {"HOT", "WARM", "NURTURE", "LOW"}

    refreshed = seed_session.get(RawSourceRecord, raw.id)
    assert refreshed.raw_status == RawStatus.PROCESSED
    assert refreshed.lead_id == result.lead_id
    assert refreshed.technologies  # normalized extraction persisted back

    lead = seed_session.get(Lead, result.lead_id)
    assert lead.company_name == "ABC Technologies Pvt Ltd"


def test_invalid_record_marked_invalid(seed_session):
    raw = _raw(seed_session, company_name=None)
    result = process_raw_record(seed_session, raw, LeadAnalysisPipeline())
    assert result.status == "invalid"
    assert seed_session.get(RawSourceRecord, raw.id).raw_status == RawStatus.INVALID


def test_process_pending_processes_new_only_and_is_idempotent(seed_session):
    _raw(seed_session, external_id="a", source_url="https://synthetic.example/jobs/a")
    _raw(seed_session, external_id="b", source_url="https://synthetic.example/jobs/b",
         title="Cloud migration program", description="Digital transformation and cloud migration to AWS.")

    first = process_pending(seed_session)
    assert first.total == 2 and first.processed == 2

    # Re-running finds no NEW records.
    second = process_pending(seed_session)
    assert second.total == 0

    # Every raw record is now linked to a lead.
    rows = seed_session.query(RawSourceRecord).all()
    assert all(r.raw_status == RawStatus.PROCESSED and r.lead_id is not None for r in rows)


def test_process_pending_real_only_skips_synthetic(seed_session):
    _raw(seed_session, external_id="syn", source_url="https://synthetic.example/jobs/syn", is_synthetic=True)
    summary = process_pending(seed_session, include_synthetic=False)
    assert summary.total == 0  # only synthetic present -> nothing processed


def test_duplicate_signal_upserts_single_lead(seed_session):
    # Two raw records with the same company + title + source_url -> one lead.
    _raw(seed_session, external_id="x")
    _raw(seed_session, external_id="x2")  # same title/company/url, different external id
    summary = process_pending(seed_session)
    assert summary.processed == 2
    # The pipeline upserts on (company, signal_title, source_url) -> one lead row.
    assert seed_session.query(Lead).count() == 1
    assert summary.leads_created == 1 and summary.leads_existed == 1
