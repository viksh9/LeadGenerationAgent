"""Tests for the synthetic sample data + database seed system."""

from collections import Counter
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from database.models import Lead
from database.session import create_session_factory, get_engine
from scripts import seed_database
from scripts.seed_database import (
    assert_reset_allowed,
    load_sample_leads,
    main,
    reset_leads,
    seed,
    select_records,
    to_analyze_request,
)
from tests.fixtures import synthetic_leads

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

    # Ready: HOT/WARM with a pitch, a recommended role, and a sufficient signal.
    ready = [
        l
        for l in leads
        if pri(l) in {"HOT", "WARM"}
        and l.recommended_pitch
        and l.poc_title
        and not (l.signal_confidence is not None and l.signal_confidence < 50)
    ]
    # Needs review: low priority or weak signal.
    review = [
        l
        for l in leads
        if pri(l) in {"LOW", "NURTURE"} or (l.signal_confidence is not None and l.signal_confidence < 50)
    ]
    assert ready, "expected some outreach-ready leads"
    assert review, "expected some leads needing review"


def test_reset_in_development(seed_session, records):
    seed(seed_session, records, reference=REFERENCE)
    removed = reset_leads(seed_session)
    assert removed == len(records)
    assert seed_session.query(Lead).count() == 0


def test_reset_refuses_production(monkeypatch):
    monkeypatch.setattr(
        "scripts.seed_database.get_settings",
        lambda: SimpleNamespace(environment="production"),
    )
    with pytest.raises(SystemExit):
        assert_reset_allowed()


def test_reset_refuses_when_env_missing(monkeypatch):
    monkeypatch.setattr(
        "scripts.seed_database.get_settings",
        lambda: SimpleNamespace(environment=""),
    )
    with pytest.raises(SystemExit):
        assert_reset_allowed()


def test_reset_allowed_in_development(monkeypatch):
    monkeypatch.setattr(
        "scripts.seed_database.get_settings",
        lambda: SimpleNamespace(environment="development"),
    )
    assert_reset_allowed()  # does not raise


def test_count_option_selects_variety(records):
    picked = select_records(records, 10)
    assert len(picked) == 10
    # spread across more than one industry
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


def _count_in(url: str) -> int:
    with create_session_factory(get_engine(url))() as s:
        return s.query(Lead).count()


def test_cli_seed_with_count(monkeypatch, tmp_path):
    url = f"sqlite:///{tmp_path / 'cli.db'}"
    monkeypatch.setattr(
        seed_database, "get_settings", lambda: SimpleNamespace(database_url=url, environment="development")
    )
    rc = main(["--count", "5", "--reference-date", "2026-09-07"])
    assert rc == 0
    assert _count_in(url) == 5


def test_cli_reset_yes(monkeypatch, tmp_path):
    url = f"sqlite:///{tmp_path / 'cli_reset.db'}"
    monkeypatch.setattr(
        seed_database, "get_settings", lambda: SimpleNamespace(database_url=url, environment="development")
    )
    main(["--count", "8", "--reference-date", "2026-09-07"])
    assert _count_in(url) == 8
    rc = main(["--reset", "--yes", "--count", "5", "--reference-date", "2026-09-07"])
    assert rc == 0
    assert _count_in(url) == 5  # reset wiped the 8, then seeded 5
