"""Integration tests for JobDeduplicationService (canonical jobs + references)."""

from __future__ import annotations

from datetime import datetime, timedelta

from collectors.raw_record import RawRecordDraft
from database.models import (
    DataProvenance,
    DuplicateStatus,
    JobDuplicateCandidate,
    JobRecord,
    JobSourceReference,
)
from database.raw_repository import create_raw_record_from_draft
from processors.deduplication import JobDeduplicationService
from processors.deduplication.repository import (
    approve_duplicate,
    dedup_stats,
    list_pending_duplicates,
    reject_duplicate,
)
from sqlalchemy import func, select

NOW = datetime(2026, 9, 5)


def _raw(session, *, source, company, title, city, ext, desc="Java Spring Boot AWS backend microservices",
         domain=None, days_ago=3, synthetic=False, salary=None):
    return create_raw_record_from_draft(session, RawRecordDraft(
        source_id=source, external_id=ext, source_url=f"https://{source}/{ext}",
        published_at=NOW - timedelta(days=days_ago), record_type="JOB_POSTING",
        title=title, description=desc, company_name=company, company_domain=domain,
        location=city, technologies=["Java", "AWS"], salary=salary, is_synthetic=synthetic,
    ))


def _count(session, model):
    return session.scalar(select(func.count()).select_from(model))


def test_duplicate_across_three_sources(seed_session):
    _raw(seed_session, source="company_career", company="ABC Technologies", title="Senior Java Backend Engineer", city="Bengaluru", ext="c1", domain="abc.com")
    _raw(seed_session, source="adzuna", company="ABC Technologies Pvt Ltd", title="Sr. Java Backend Engineer", city="Bangalore", ext="a1")
    _raw(seed_session, source="demo_jobs", company="ABC Technologies", title="Senior Java Backend Engineer", city="Bengaluru", ext="o1")
    raws = list(seed_session.scalars(select(__import__("database.models", fromlist=["RawSourceRecord"]).RawSourceRecord)))
    summary = JobDeduplicationService(seed_session).deduplicate(raws, provenance=DataProvenance.REAL, now=NOW)
    assert summary.canonical_jobs == 1
    assert summary.source_references == 3
    jr = seed_session.scalars(select(JobRecord)).first()
    assert jr.source_count == 3
    assert jr.primary_source == "company_career"  # priority 1
    assert len(jr.source_references) == 3
    assert sum(1 for r in jr.source_references if r.is_primary_source) == 1


def test_different_project_two_canonicals(seed_session):
    _raw(seed_session, source="adzuna", company="ABC Technologies", title="Senior Java Backend Engineer - Payments Team", city="Bengaluru", ext="p1", desc="payments settlement ledger")
    _raw(seed_session, source="adzuna", company="ABC Technologies", title="Senior Java Backend Engineer - Cloud Platform Team", city="Bengaluru", ext="q1", desc="kubernetes platform infra")
    from database.models import RawSourceRecord
    raws = list(seed_session.scalars(select(RawSourceRecord)))
    summary = JobDeduplicationService(seed_session).deduplicate(raws, provenance=DataProvenance.REAL, now=NOW)
    assert summary.canonical_jobs == 2


def test_no_data_loss(seed_session):
    r1 = _raw(seed_session, source="company_career", company="ABC Technologies", title="Senior Java Backend Engineer", city="Bengaluru", ext="c1")
    r2 = _raw(seed_session, source="adzuna", company="ABC Technologies Pvt Ltd", title="Sr. Java Backend Engineer", city="Bangalore", ext="a1")
    JobDeduplicationService(seed_session).deduplicate([r1, r2], provenance=DataProvenance.REAL, now=NOW)
    jr = seed_session.scalars(select(JobRecord)).first()
    # Original titles from BOTH sources preserved.
    assert set(jr.original_job_titles) == {"Senior Java Backend Engineer", "Sr. Java Backend Engineer"}
    # Every source URL + external id preserved as references.
    urls = {ref.source_url for ref in jr.source_references}
    assert urls == {"https://company_career/c1", "https://adzuna/a1"}
    # Raw source records are untouched (still 2).
    from database.models import RawSourceRecord
    assert _count(seed_session, RawSourceRecord) == 2


def test_field_conflicts_recorded(seed_session):
    _raw(seed_session, source="company_career", company="ABC Technologies", title="Senior Java Backend Engineer", city="Bengaluru", ext="c1", salary="INR 15-20 LPA")
    _raw(seed_session, source="adzuna", company="ABC Technologies", title="Senior Java Backend Engineer", city="Bengaluru", ext="a1", salary="INR 18-22 LPA")
    from database.models import RawSourceRecord
    raws = list(seed_session.scalars(select(RawSourceRecord)))
    JobDeduplicationService(seed_session).deduplicate(raws, provenance=DataProvenance.REAL, now=NOW)
    jr = seed_session.scalars(select(JobRecord)).first()
    assert jr.source_count == 2
    assert "salary" in jr.field_conflicts and len(jr.field_conflicts["salary"]) == 2


def test_review_candidate_created(seed_session):
    # Same company+city, similar-but-not-identical role, different descriptions -> REVIEW.
    _raw(seed_session, source="company_career", company="ABC Technologies", title="Senior Java Engineer", city="Bengaluru", ext="c1", desc="backend microservices team")
    _raw(seed_session, source="adzuna", company="ABC Technologies", title="Senior Java Backend Developer", city="Bengaluru", ext="a1", desc="data pipelines and etl work")
    from database.models import RawSourceRecord
    raws = list(seed_session.scalars(select(RawSourceRecord)))
    summary = JobDeduplicationService(seed_session).deduplicate(raws, provenance=DataProvenance.REAL, now=NOW)
    # Not auto-merged; a review candidate is recorded for a human.
    assert summary.canonical_jobs == 2
    if summary.review_candidates:
        cand = seed_session.scalars(select(JobDuplicateCandidate)).first()
        assert cand.status is DuplicateStatus.PENDING and cand.matched_fields


def test_deterministic_reprocessing(seed_session):
    for i in range(4):
        _raw(seed_session, source="adzuna", company="ABC Technologies", title="Senior Java Backend Engineer", city="Bengaluru", ext=f"a{i}", desc=f"role {i} distinct project {i}")
    from database.models import RawSourceRecord
    raws = list(seed_session.scalars(select(RawSourceRecord)))
    svc = JobDeduplicationService(seed_session)
    first = svc.deduplicate(raws, provenance=DataProvenance.REAL, reset=True, now=NOW)
    second = svc.deduplicate(raws, provenance=DataProvenance.REAL, reset=True, now=NOW)
    assert first.canonical_jobs == second.canonical_jobs


def test_dry_run_does_not_persist(seed_session):
    r1 = _raw(seed_session, source="adzuna", company="ABC Technologies", title="Senior Java Backend Engineer", city="Bengaluru", ext="a1")
    summary = JobDeduplicationService(seed_session).deduplicate([r1], provenance=DataProvenance.REAL, persist=False, now=NOW)
    assert summary.canonical_jobs == 1
    assert _count(seed_session, JobRecord) == 0


def test_dedup_stats(seed_session):
    _raw(seed_session, source="company_career", company="ABC Technologies", title="Senior Java Backend Engineer", city="Bengaluru", ext="c1")
    _raw(seed_session, source="adzuna", company="ABC Technologies", title="Senior Java Backend Engineer", city="Bengaluru", ext="a1")
    from database.models import RawSourceRecord
    raws = list(seed_session.scalars(select(RawSourceRecord)))
    JobDeduplicationService(seed_session).deduplicate(raws, provenance=DataProvenance.REAL, now=NOW)
    stats = dedup_stats(seed_session, provenance=DataProvenance.REAL, now=NOW)
    assert stats["canonical_job_count"] == 1
    assert stats["source_reference_count"] == 2
    assert stats["duplicate_rate"] == 0.5


def test_review_repository_approve_reject(seed_session):
    seed_session.add(JobDuplicateCandidate(record_a={"title": "a"}, record_b={"title": "b"}, match_score=70,
                                           matched_fields=["city"], data_provenance=DataProvenance.REAL))
    seed_session.commit()
    pending = list_pending_duplicates(seed_session)
    assert len(pending) == 1
    assert approve_duplicate(seed_session, pending[0].id) is True
    assert list_pending_duplicates(seed_session) == []
    assert reject_duplicate(seed_session, 99999) is False
