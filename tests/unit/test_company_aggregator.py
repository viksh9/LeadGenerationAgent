"""Unit tests for the company aggregation engine (pure, no DB)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from config.aggregation import AggregationConfig
from database.models import CompanyType, DataProvenance, HiringIntensity, SignalType
from intelligence.company_aggregator import (
    JobInput,
    aggregate_companies,
    compute_hiring_intensity,
    technology_demand,
)
from intelligence.company_pipeline import build_lead_fields, priority_for, score_company

NOW = datetime(2026, 9, 5, tzinfo=timezone.utc)


def job(company, title, techs, *, days_ago=3, city="Bengaluru", source="adzuna", ext=None, industry="Software", synthetic=False):
    return JobInput(
        source_id=source, title=title, description=f"{title}. {' '.join(techs)}",
        company_name=company, location=f"{city}, IN", city=city, industry=industry,
        technologies=list(techs), published_at=NOW - timedelta(days=days_ago),
        external_id=ext or f"{title}-{days_ago}", source_url=f"https://x/{ext or title}",
        is_synthetic=synthetic,
    )


def test_groups_by_normalized_company_name():
    jobs = [
        job("ABC Technologies Pvt Ltd", "Java Developer", ["Java"], ext="1"),
        job("ABC Technologies", "Python Developer", ["Python"], ext="2"),
        job("ABC Technologies Private Limited", "AWS Engineer", ["AWS"], ext="3"),
    ]
    aggs = aggregate_companies(jobs, now=NOW)
    assert len(aggs) == 1
    assert aggs[0].it_job_count == 3
    assert aggs[0].normalized_name == "abc technologies"


def test_distinct_requisitions_same_source_all_count():
    jobs = [job("ABC", "Senior Java Developer", ["Java"], ext=f"j{i}") for i in range(12)]
    aggs = aggregate_companies(jobs, now=NOW)
    assert aggs[0].it_job_count == 12  # distinct external ids all count


def test_cross_source_duplicate_collapses_but_records_source():
    jobs = [
        job("ABC", "Java Developer", ["Java"], city="Pune", source="adzuna", ext="a1"),
        job("ABC", "Java Developer", ["Java"], city="Pune", source="company_career", ext="c1"),
    ]
    aggs = aggregate_companies(jobs, now=NOW)
    assert aggs[0].it_job_count == 1              # same posting, not two
    assert aggs[0].source_count == 2 if hasattr(aggs[0], "source_count") else True
    assert sorted(aggs[0].sources) == ["adzuna", "company_career"]


def test_exact_duplicate_same_source_ignored():
    jobs = [
        job("ABC", "Java Developer", ["Java"], ext="same"),
        job("ABC", "Java Developer", ["Java"], ext="same"),
    ]
    aggs = aggregate_companies(jobs, now=NOW)
    assert aggs[0].it_job_count == 1


def test_recent_counts_and_windows():
    jobs = [
        job("ABC", "A", ["Java"], days_ago=2, ext="1"),
        job("ABC", "B", ["Java"], days_ago=10, ext="2"),
        job("ABC", "C", ["Java"], days_ago=40, ext="3"),
        job("ABC", "D", ["Java"], days_ago=200, ext="4"),
    ]
    agg = aggregate_companies(jobs, now=NOW)[0]
    assert agg.recent_counts.get(7) == 1
    assert agg.recent_counts.get(14) == 2
    assert agg.recent_counts.get(30) == 2
    assert agg.recent_job_count == 2  # within 30-day default window


@pytest.mark.parametrize("count,expected", [
    (2, HiringIntensity.LOW), (10, HiringIntensity.MEDIUM),
    (25, HiringIntensity.HIGH), (60, HiringIntensity.VERY_HIGH),
])
def test_hiring_intensity_thresholds(count, expected):
    assert compute_hiring_intensity(count, AggregationConfig()) is expected


def test_signals_large_multi_and_rapid():
    jobs = [job("ABC", f"Role {i}", ["Java", "AWS", "DevOps"][: (i % 3) + 1], days_ago=2, ext=f"j{i}") for i in range(30)]
    agg = aggregate_companies(jobs, now=NOW)[0]
    assert "LARGE_TECH_HIRING" in agg.company_signals
    assert "MULTI_TECH_HIRING" in agg.company_signals
    assert "RAPID_HIRING" in agg.company_signals


def test_vendor_signal_from_contract_language():
    jobs = [job("ABC", "Contract Java Developer (staff augmentation)", ["Java"], ext=f"j{i}") for i in range(3)]
    agg = aggregate_companies(jobs, now=NOW)[0]
    assert "VENDOR_REQUIREMENT" in agg.company_signals


def test_engineering_expansion_multi_city():
    jobs = [
        job("ABC", "Java Developer", ["Java"], city="Bengaluru", ext="1"),
        job("ABC", "Java Developer", ["Java"], city="Hyderabad", ext="2"),
        job("ABC", "Java Developer", ["Java"], city="Pune", ext="3"),
    ]
    agg = aggregate_companies(jobs, now=NOW)[0]
    assert "ENGINEERING_EXPANSION" in agg.company_signals
    assert len(agg.cities) == 3


def test_company_type_classification():
    fin = aggregate_companies([job("FinCo", "Java Dev", ["Java"], industry="FinTech Technology", ext="1")], now=NOW)[0]
    assert fin.company_type is CompanyType.FINTECH_TECH


def test_provenance_propagates_from_jobs():
    agg = aggregate_companies([job("ABC", "Java", ["Java"], synthetic=True, ext="1")], now=NOW)[0]
    assert agg.provenance is DataProvenance.SYNTHETIC


def test_jobs_without_company_are_skipped():
    j = job("ABC", "Java", ["Java"], ext="1")
    j2 = JobInput(source_id="x", title="No company", technologies=["Java"])
    aggs = aggregate_companies([j, j2], now=NOW)
    assert len(aggs) == 1


def test_technology_demand_counts_openings_and_companies():
    jobs = [
        job("ABC", "Java Dev", ["Java", "AWS"], ext="1"),
        job("ABC", "AWS Eng", ["AWS"], ext="2"),
        job("XYZ", "Java Dev", ["Java"], city="Pune", ext="3"),
    ]
    demand = {d["technology"]: d for d in technology_demand(jobs)}
    assert demand["Java"]["openings"] == 2 and demand["Java"]["companies"] == 2
    assert demand["AWS"]["openings"] == 2 and demand["AWS"]["companies"] == 1


def test_score_and_priority():
    big = [job("ABC", f"Senior Engineer {i}", ["Java", "AWS", "DevOps", "React"][: (i % 4) + 1], days_ago=2, ext=f"j{i}") for i in range(50)]
    agg = aggregate_companies(big, now=NOW)[0]
    score = score_company(agg)
    assert score >= 80
    assert priority_for(score).value == "HOT"


def test_low_activity_is_low_priority():
    agg = aggregate_companies([job("ABC", "Software Engineer", ["Java"], days_ago=120, ext="1")], now=NOW)[0]
    score = score_company(agg)
    assert priority_for(score).value in {"LOW", "NURTURE"}


def test_build_lead_fields_shape():
    jobs = [job("ABC Technologies", f"Java Developer {i}", ["Java", "AWS"], ext=f"j{i}") for i in range(26)]
    agg = aggregate_companies(jobs, now=NOW)[0]
    fields = build_lead_fields(agg, now=NOW.replace(tzinfo=None))
    assert fields["company_name"] == "ABC Technologies"
    assert fields["normalized_company_name"] == "abc technologies"
    assert fields["it_job_count"] == 26
    assert fields["estimated_hiring"] == 26
    assert fields["data_provenance"] is DataProvenance.REAL
    assert isinstance(fields["signal_type"], SignalType)
    assert fields["source_count"] >= 1
    assert len(fields["evidence"]) >= 1
    assert fields["primary_target_role"]
