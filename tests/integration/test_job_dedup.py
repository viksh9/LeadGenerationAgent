"""Integration tests for the canonical job layer (normalize -> dedupe)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from collectors.raw_record import RawRecordDraft
from database.models import DataProvenance, JobRecord, JobSourceReference
from database.raw_repository import create_raw_record_from_draft
from ingestion.job_pipeline import build_job_records
from sqlalchemy import func, select

NOW = datetime(2026, 9, 5)


def _raw(session, *, company="Ravi Technologies Pvt Ltd", title="Java Developer", techs=("Java",),
         city="Bengaluru", source="adzuna", ext=None, days_ago=3, synthetic=False):
    draft = RawRecordDraft(
        source_id=source, external_id=ext or f"{source}-{title}-{days_ago}",
        source_url=f"https://x/{ext or title}", published_at=NOW - timedelta(days=days_ago),
        record_type="JOB_POSTING", title=title, description=f"{title}. {' '.join(techs)}",
        company_name=company, location=f"{city}, India", industry="Software",
        technologies=list(techs), is_synthetic=synthetic,
    )
    return create_raw_record_from_draft(session, draft)


def _count(session, model):
    return session.scalar(select(func.count()).select_from(model))


def test_twenty_distinct_requisitions_stay_distinct(seed_session):
    for i in range(20):
        _raw(seed_session, title="Senior Java Developer", ext=f"j{i}")
    summary = build_job_records(seed_session, provenance=DataProvenance.REAL, now=NOW)
    assert summary.canonical_created == 20  # same title, distinct ids -> 20 openings
    assert _count(seed_session, JobRecord) == 20


def test_duplicate_across_two_sources(seed_session):
    _raw(seed_session, title="Java Developer", city="Pune", source="adzuna", ext="a1")
    _raw(seed_session, title="Java Developer", city="Pune", source="company_career", ext="c1")
    build_job_records(seed_session, provenance=DataProvenance.REAL, now=NOW)
    assert _count(seed_session, JobRecord) == 1
    jr = seed_session.scalars(select(JobRecord)).first()
    assert jr.source_count == 2
    assert len(jr.source_references) == 2


def test_duplicate_across_three_sources(seed_session):
    for src in ("adzuna", "company_career", "demo_jobs"):
        _raw(seed_session, title="AWS Engineer", city="Hyderabad", source=src, ext=f"{src}-1", techs=("AWS",))
    build_job_records(seed_session, provenance=DataProvenance.REAL, now=NOW)
    jr = seed_session.scalars(select(JobRecord)).first()
    assert _count(seed_session, JobRecord) == 1
    assert jr.source_count == 3
    # Canonical/primary source is the highest-priority one (career page).
    assert jr.primary_source == "company_career"


def test_missing_company_skipped(seed_session):
    _raw(seed_session, company="Ravi Technologies", ext="ok")
    _raw(seed_session, company=None, ext="bad")
    summary = build_job_records(seed_session, provenance=DataProvenance.REAL, now=NOW)
    assert summary.canonical_created == 1
    assert summary.errors  # the no-company job recorded an error


def test_real_and_synthetic_separated(seed_session):
    _raw(seed_session, title="Java Developer", ext="r1", synthetic=False)
    _raw(seed_session, title="Java Developer", ext="s1", source="demo_jobs", synthetic=True)
    build_job_records(seed_session, provenance=DataProvenance.REAL, now=NOW)
    build_job_records(seed_session, provenance=DataProvenance.SYNTHETIC, now=NOW)
    real = seed_session.scalars(select(JobRecord).where(JobRecord.data_provenance == DataProvenance.REAL)).all()
    synth = seed_session.scalars(select(JobRecord).where(JobRecord.data_provenance == DataProvenance.SYNTHETIC)).all()
    assert len(real) == 1 and len(synth) == 1


def test_idempotent_rerun(seed_session):
    for i in range(5):
        _raw(seed_session, title="Java Developer", ext=f"j{i}")
    build_job_records(seed_session, provenance=DataProvenance.REAL, now=NOW)
    second = build_job_records(seed_session, provenance=DataProvenance.REAL, now=NOW)
    assert _count(seed_session, JobRecord) == 5           # no duplicates created
    assert second.canonical_created == 0
    assert _count(seed_session, JobSourceReference) == 5  # refs not duplicated


def test_expired_and_recent_flags_via_normalization(seed_session):
    _raw(seed_session, title="Java Developer", ext="recent", days_ago=3)
    _raw(seed_session, title="Python Developer", ext="old", days_ago=200, techs=("Python",))
    build_job_records(seed_session, provenance=DataProvenance.REAL, now=NOW)
    recs = {r.original_job_title: r for r in seed_session.scalars(select(JobRecord))}
    assert recs["Java Developer"].published_at is not None
    assert recs["Python Developer"].published_at < NOW - timedelta(days=180)
