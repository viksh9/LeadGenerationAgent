"""Data-integrity tests enforcing the real-data-only policy.

These assert the invariants the platform must hold:
  * an empty database is a valid state and every list endpoint returns empty
    collections (never fabricated records);
  * write guards reject synthetic/demo and source-less REAL business records
    when enforcement is active (production/staging);
  * the audit correctly detects synthetic records and reports a clean database
    once they are purged;
  * source connectivity is never reported CONNECTED from configuration alone.

The guards are exercised with an explicit ``environment`` so these tests are
deterministic and do not depend on the ambient APP_ENV.
"""

from __future__ import annotations

import pytest

from database.integrity import (
    RealDataViolation,
    audit_database,
    enforcement_active,
    guard_lead_fields,
    guard_provenance,
    purge_synthetic,
)
from database.models import DataProvenance, Lead
from database.repository import create_lead


# --------------------------------------------------------------------------- #
# Empty database is a valid, honest state
# --------------------------------------------------------------------------- #
def test_empty_db_leads_endpoint_returns_empty(client):
    body = client.get("/leads").json()
    assert body["total"] == 0
    assert body["items"] == []


def test_empty_db_companies_endpoint_returns_empty(client):
    body = client.get("/companies").json()
    assert body["total"] == 0
    assert body["items"] == []


def test_empty_db_technology_demand_returns_empty(client):
    body = client.get("/leads/technology-demand").json()
    assert body["items"] == []


def test_empty_db_audit_is_clean(seed_session):
    audit = audit_database(seed_session)
    assert audit.total_records == 0
    assert audit.synthetic_total == 0
    assert audit.is_clean is True


# --------------------------------------------------------------------------- #
# Write guards — enforcement environments
# --------------------------------------------------------------------------- #
def test_enforcement_active_by_environment():
    assert enforcement_active("production") is True
    assert enforcement_active("staging") is True
    assert enforcement_active("development") is False
    assert enforcement_active("test") is False


def test_guard_rejects_synthetic_in_production():
    with pytest.raises(RealDataViolation):
        guard_provenance(DataProvenance.SYNTHETIC, entity="lead", environment="production")


def test_guard_allows_synthetic_in_development():
    # No exception in a non-enforcing environment.
    guard_provenance(DataProvenance.SYNTHETIC, entity="lead", environment="development")


def test_guard_rejects_real_without_source_in_production():
    with pytest.raises(RealDataViolation):
        guard_lead_fields(
            {"company_name": "Acme", "data_provenance": DataProvenance.REAL},
            environment="production",
        )


def test_guard_accepts_real_with_source_in_production():
    guard_lead_fields(
        {
            "company_name": "Acme",
            "data_provenance": DataProvenance.REAL,
            "source_url": "https://careers.acme.example/jobs/1",
        },
        environment="production",
    )


def test_guard_accepts_real_with_evidence_list():
    guard_lead_fields(
        {
            "company_name": "Acme",
            "data_provenance": DataProvenance.REAL,
            "evidence": [{"source": "adzuna", "source_url": "https://x.example/1"}],
        },
        environment="production",
    )


# --------------------------------------------------------------------------- #
# create_lead honours the guard when enforcement is active
# --------------------------------------------------------------------------- #
def test_create_lead_source_less_blocked_in_production(seed_session, monkeypatch):
    from config.settings import Settings

    # Force enforcement on regardless of ambient env.
    monkeypatch.setattr("config.settings.get_settings",
                        lambda: Settings(environment="production"))
    with pytest.raises(RealDataViolation):
        create_lead(seed_session, company_name="Ghost Corp")


def test_create_lead_allowed_in_development(seed_session, monkeypatch):
    from config.settings import Settings

    monkeypatch.setattr("config.settings.get_settings",
                        lambda: Settings(environment="development"))
    lead = create_lead(seed_session, company_name="Dev Corp")
    assert lead.id is not None


# --------------------------------------------------------------------------- #
# Audit + purge round-trip
# --------------------------------------------------------------------------- #
def test_purge_removes_synthetic_keeps_real(seed_session):
    seed_session.add_all([
        Lead(company_name="Synth A", data_provenance=DataProvenance.SYNTHETIC),
        Lead(company_name="Synth B", data_provenance=DataProvenance.SYNTHETIC),
        Lead(company_name="Real A", data_provenance=DataProvenance.REAL,
             source_url="https://x.example/a", source_count=1),
    ])
    seed_session.commit()

    before = audit_database(seed_session)
    assert before.synthetic_total == 2
    assert before.is_clean is False

    removed = purge_synthetic(seed_session)
    assert removed.get("leads") == 2

    after = audit_database(seed_session)
    assert after.synthetic_total == 0
    assert after.by_table("leads").real == 1
    assert after.is_clean is True


# --------------------------------------------------------------------------- #
# Source connectivity is truthful
# --------------------------------------------------------------------------- #
def test_sources_never_connected_without_live_probe(client):
    body = client.get("/sources").json()
    assert body["any_connected"] is False
    assert body["connected_count"] == 0
    assert all(item["status"] != "CONNECTED" for item in body["items"])


def test_sources_report_is_truthful_about_implementation(client):
    body = client.get("/sources").json()
    by_id = {item["source_id"]: item for item in body["items"]}
    # Adzuna collector exists but has no credentials in a clean test env.
    assert by_id["adzuna"]["collector_implemented"] is True
    assert by_id["adzuna"]["status"] in {"NOT_CONFIGURED", "CONFIGURED"}
    # Sources with no collector must not claim to be implemented.
    assert by_id["government_open_data"]["collector_implemented"] is False
    assert by_id["government_open_data"]["status"] == "PLANNED"
