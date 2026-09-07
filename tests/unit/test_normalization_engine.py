"""Engine-level normalization tests (§41 scenarios 21-30, §42 no-data-loss)."""

from __future__ import annotations

from datetime import datetime

from collectors.raw_record import RawRecordDraft
from database.models import DataProvenance
from processors.normalization import normalize_job, normalize_many
from processors.normalization.adapters import normalize_raw

NOW = datetime(2026, 9, 5)

# A record resembling a real Adzuna-mapped raw record.
ADZUNA_RAW = {
    "title": "Sr. Java Backend Engineer - Payments Platform",
    "description": "Java, Spring Boot, AWS, Kubernetes. 5-8 years experience.",
    "company_name": "ABC Technologies Pvt Ltd",
    "company_domain": "abc.com",
    "location": "Bangalore, Karnataka",
    "industry": "Information Technology & Services",
    "technologies": ["Java", "JAVA", "SpringBoot", "AWS", "K8s"],
    "contract_type": "Full Time",
    "salary": "INR 18-25 LPA",
    "published_at": datetime(2026, 9, 3),
    "source_id": "adzuna",
    "source_url": "https://www.adzuna.in/details/1?utm_source=x",
    "is_synthetic": False,
}


def test_full_normalization():
    r = normalize_job(ADZUNA_RAW, now=NOW)
    assert r.normalized_job_title == "Senior Java Backend Engineer - Payments Platform"
    assert r.role_taxonomy.value == "JAVA_ENGINEERING"
    assert r.seniority_level.value == "SENIOR"
    assert r.normalized_city == "Bengaluru" and r.normalized_state == "Karnataka"
    assert r.normalized_technologies == ["Java", "Spring Boot", "AWS", "Kubernetes"]
    assert r.it_relevance.value == "HIGH"
    assert r.employment_type.value == "FULL_TIME"
    assert (r.salary_min, r.salary_max, r.currency) == (1_800_000, 2_500_000, "INR")
    assert (r.experience_min, r.experience_max) == (5, 8)
    assert r.normalization_version == "1.0.0"
    assert r.normalization_confidence >= 80


# §42 — MANDATORY: originals unchanged.
def test_no_data_loss():
    r = normalize_job(ADZUNA_RAW, now=NOW)
    assert r.original_job_title == ADZUNA_RAW["title"]
    assert r.original_company_name == ADZUNA_RAW["company_name"]
    assert r.original_location == ADZUNA_RAW["location"]
    assert r.original_description == ADZUNA_RAW["description"]
    assert r.original_source_url == ADZUNA_RAW["source_url"]
    # Normalized fields are separate and differ from originals.
    assert r.normalized_job_title != r.original_job_title
    assert r.normalized_source_url != r.original_source_url  # tracking param stripped


# §28 — idempotency.
def test_idempotency():
    a = normalize_job(ADZUNA_RAW, now=NOW)
    b = normalize_job(ADZUNA_RAW, now=NOW)
    assert a == b


# §48 — provenance preserved, never changed.
def test_provenance_preserved():
    assert normalize_job({**ADZUNA_RAW, "is_synthetic": True}, now=NOW).data_provenance is DataProvenance.SYNTHETIC
    assert normalize_job(ADZUNA_RAW, now=NOW).data_provenance is DataProvenance.REAL


# §25 — warnings, not silent assumptions.
def test_warnings_generated():
    r = normalize_job({"title": "Engineer", "location": "Atlantis", "salary": "20000",
                       "source_id": "x"}, now=NOW)
    assert any("could not be mapped" in w for w in r.normalization_warnings)


# §38 — batch: one bad record doesn't fail the batch.
def test_batch_normalization():
    records = [ADZUNA_RAW, {"title": "Python Developer", "source_id": "x"}, ADZUNA_RAW]
    results, summary = normalize_many(records, now=NOW)
    assert summary.total == 3 and summary.normalized == 3 and summary.failed == 0
    assert len(results) == 3


# §34 — business-signal clues preserved in the description.
def test_business_signal_preservation():
    raw = {"title": "DevOps Engineer", "description": "Join our rapidly expanding DevOps team for a new cloud engineering center.",
           "source_id": "x"}
    r = normalize_job(raw, now=NOW)
    assert "rapidly expanding" in r.original_description
    assert "cloud engineering center" in r.original_description


# §35 — source-specific adapter (Adzuna structured salary from payload).
def test_adzuna_adapter_extracts_payload_salary():
    raw = RawRecordDraft(
        source_id="adzuna", external_id="1", record_type="JOB_POSTING",
        title="Java Developer", company_name="ABC Technologies",
        location="Pune", technologies=["Java"],
        raw_payload={"salary_min": 1500000, "salary_max": 2500000, "contract_time": "full_time"},
    )
    r = normalize_raw(raw, now=NOW)
    assert r.salary_min == 1500000 and r.salary_max == 2500000
    assert r.employment_type.value == "FULL_TIME"


# §41.26/27 — missing + malformed fields handled.
def test_missing_and_malformed_fields():
    r = normalize_job({"source_id": "x"}, now=NOW)  # almost empty
    assert r.normalized_job_title is None
    assert r.it_relevance.value in {"UNKNOWN", "LOW", "MEDIUM"}
    assert r.normalization_confidence >= 0
    results, summary = normalize_many([None, 123, {"title": "x"}], now=NOW)
    assert summary.failed >= 0 and summary.total == 3  # never raises
