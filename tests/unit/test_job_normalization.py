"""Unit tests for JobNormalizationService (raw record -> NormalizedJob)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from collectors.raw_record import RawRecordDraft
from database.models import DataProvenance, JobStatus, RemoteType
from ingestion.job_normalization import JobNormalizationService

NOW = datetime(2026, 9, 5)


def _raw(**overrides):
    data = dict(
        source_id="adzuna",
        external_id="A-1",
        source_url="https://x/A-1",
        published_at=datetime(2026, 9, 3, tzinfo=timezone.utc),
        record_type="JOB_POSTING",
        title="Senior Java Backend Engineer - Payments Platform",
        description="Java, Spring Boot and AWS. Kubernetes a plus.",
        company_name="Ravi Technologies Pvt Ltd",
        company_domain="ravitech.example",
        location="Bangalore",
        industry="IT Services",
        technologies=["Java", "AWS"],
        contract_type="full_time",
        is_synthetic=False,
    )
    data.update(overrides)
    return RawRecordDraft(**data)


def test_preserves_original_title_and_derives_role():
    nj = JobNormalizationService().normalize(_raw(), now=NOW)
    assert nj.original_job_title == "Senior Java Backend Engineer - Payments Platform"
    assert nj.normalized_role == "Backend Engineer"  # canonical, original untouched


def test_location_normalized():
    nj = JobNormalizationService().normalize(_raw(location="Bangalore"), now=NOW)
    assert nj.city == "Bengaluru"
    assert nj.state == "Karnataka"
    assert nj.country == "India"


def test_technologies_and_company_identity():
    nj = JobNormalizationService().normalize(_raw(), now=NOW)
    assert "Java" in nj.technologies and "AWS" in nj.technologies
    assert nj.normalized_company_name == "ravi technologies"
    assert nj.company_domain == "ravitech.example"


def test_data_quality_high_vs_low():
    full = JobNormalizationService().normalize(_raw(), now=NOW)
    sparse = JobNormalizationService().normalize(
        _raw(description=None, source_url=None, published_at=None, technologies=[], location=None, external_id=None),
        now=NOW,
    )
    assert full.data_quality_score > sparse.data_quality_score
    assert full.data_quality_score >= 90
    # company + title (+ a tech still detected from the title) — no url/date/desc/location.
    assert sparse.data_quality_score <= 50


def test_source_confidence_by_source():
    adz = JobNormalizationService().normalize(_raw(source_id="adzuna"), now=NOW)
    career = JobNormalizationService().normalize(_raw(source_id="company_career"), now=NOW)
    assert career.source_confidence > adz.source_confidence


def test_job_status_expired_from_valid_through():
    raw = _raw(raw_payload={"valid_through": "2026-08-01T00:00:00Z"})
    nj = JobNormalizationService().normalize(raw, now=NOW)
    assert nj.job_status is JobStatus.EXPIRED


def test_job_status_unknown_by_default():
    assert JobNormalizationService().normalize(_raw(), now=NOW).job_status is JobStatus.UNKNOWN


def test_salary_parsed_from_payload():
    raw = _raw(raw_payload={"salary_min": 1500000, "salary_max": 2500000, "salary_currency": "INR"})
    nj = JobNormalizationService().normalize(raw, now=NOW)
    assert nj.salary_min == 1500000 and nj.salary_max == 2500000 and nj.currency == "INR"


def test_provenance_and_canonical_key():
    nj = JobNormalizationService().normalize(_raw(is_synthetic=True), now=NOW)
    assert nj.data_provenance is DataProvenance.SYNTHETIC
    assert nj.canonical_key == "ravi technologies|backend engineer|bengaluru"


def test_remote_type_from_location():
    nj = JobNormalizationService().normalize(_raw(location="Remote - India"), now=NOW)
    assert nj.remote_type is RemoteType.REMOTE
