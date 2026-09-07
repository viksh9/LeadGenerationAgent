"""Tests for the synthetic sample data + test seeding helpers.

The seeding utilities are test-only (``tests/fixtures/seeding.py``); the previous
production ``scripts/seed_database.py`` was removed under the real-data-only
policy. These tests still exercise the real analysis pipeline against known
synthetic input, using an isolated per-test database.
"""

from collections import Counter
from datetime import datetime, timezone

import pytest

from database.models import Lead
from tests.fixtures import synthetic_leads
from tests.fixtures.seeding import (
    load_sample_leads,
    reset_leads,
    seed,
    select_records,
    to_analyze_request,
)

REFERENCE = datetime(2026, 9, 7, tzinfo=timezone.utc)


@pytest.fixture
def records():
    return load_sample_leads()


def test_sample_data_loads(records):
    assert isinstance(records, list)
    assert len(records) >= 30


def test_sample_data_validates(records):
    for rec in records:
        req = to_analyze_request(rec, REFERENCE)
        assert req.company_name
        assert req.signal_date is not None


def test_all_fixtures_build_valid_requests():
    for build in synthetic_leads.ALL_BUILDERS.values():
        req = to_analyze_request(build(), REFERENCE)
        assert req.company_name


def test_invalid_record_raises():
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        to_analyze_request({"company_name": ""}, REFERENCE)  # empty company name


def test_seed_creates_records(seed_session, records):
    summary = seed(seed_session, records, reference=REFERENCE)
    assert summary.created == len(records)
    assert summary.skipped == 0
    assert summary.failed == 0
    assert seed_session.query(Lead).count() == len(records)


def test_seeded_records_are_synthetic(seed_session, records):
    """Test seeding must tag every record SYNTHETIC — never REAL."""
    from database.models import DataProvenance

    seed(seed_session, records, reference=REFERENCE)
    provenances = {row.data_provenance for row in seed_session.query(Lead).all()}
    assert provenances == {DataProvenance.SYNTHETIC}


def test_reseed_prevents_duplicates(seed_session, records):
    seed(seed_session, records, reference=REFERENCE)
    second = seed(seed_session, records, reference=REFERENCE)
    assert second.created == 0
    assert second.skipped == len(records)
    assert seed_session.query(Lead).count() == len(records)


def test_distributions_are_varied(seed_session, records):
    summary = seed(seed_session, records, reference=REFERENCE)
    # All four priorities represented.
    assert set(summary.priority) == {"HOT", "WARM", "NURTURE", "LOW"}
    # All four target industries present.
    assert {"IT", "BFSI", "FMCG", "Healthcare"} <= set(summary.industry)
    # Multiple opportunity + signal types.
    assert len(summary.opportunity) >= 3
    assert len(summary.signal) >= 3


def test_company_aggregation_has_multi_lead_companies(seed_session, records):
    seed(seed_session, records, reference=REFERENCE)
    counts = Counter(row.company_name for row in seed_session.query(Lead).all())
    assert max(counts.values()) > 1  # at least one company with multiple leads


def test_poc_roles_recommended(seed_session, records):
    seed(seed_session, records, reference=REFERENCE)
    roles = {row.poc_title for row in seed_session.query(Lead).all() if row.poc_title}
    assert roles  # role recommendations exist
    assert any("Engineering" in r or r in {"CTO", "CIO"} for r in roles)


def test_outreach_ready_and_review_cases(seed_session, records):
    seed(seed_session, records, reference=REFERENCE)
    leads = seed_session.query(Lead).all()

    def pri(lead):
        return lead.lead_priority.value if hasattr(lead.lead_priority, "value") else lead.lead_priority

    ready = [
        l
        for l in leads
        if pri(l) in {"HOT", "WARM"}
        and l.recommended_pitch
        and l.poc_title
        and not (l.signal_confidence is not None and l.signal_confidence < 50)
    ]
    review = [
        l
        for l in leads
        if pri(l) in {"LOW", "NURTURE"} or (l.signal_confidence is not None and l.signal_confidence < 50)
    ]
    assert ready, "expected some outreach-ready leads"
    assert review, "expected some leads needing review"


def test_reset_clears_records(seed_session, records):
    seed(seed_session, records, reference=REFERENCE)
    removed = reset_leads(seed_session)
    assert removed == len(records)
    assert seed_session.query(Lead).count() == 0


def test_count_option_selects_variety(records):
    picked = select_records(records, 10)
    assert len(picked) == 10
    assert len({r["industry"] for r in picked}) > 1


def test_count_option_generates_distinct_variants(records):
    picked = select_records(records, 50)
    assert len(picked) == 50
    keys = {(r["company_name"], r["signal_title"]) for r in picked}
    assert len(keys) == 50  # no exact duplicates


def test_count_seeds_requested_number(seed_session, records):
    picked = select_records(records, 12)
    summary = seed(seed_session, picked, reference=REFERENCE)
    assert summary.created == 12
    assert seed_session.query(Lead).count() == 12
