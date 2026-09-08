"""Tests for the Prompt 41 validation/audit tooling (§3, §4, §21, §51, §52).

Uses isolated throwaway databases; verifies the audits report the truth (real
counts, honest GO/NO-GO) and never fabricate. No synthetic data enters any shared
DB — every row here is built in a per-test tmp DB.
"""

from __future__ import annotations

from datetime import datetime

from app.provenance_audit import provenance_report
from app.quality_audit import INSUFFICIENT, quality_report
from app.report import go_no_go, real_data_scorecard
from app.source_inventory import source_inventory
from app.synthetic_audit import db_synthetic_report
from app.live_audit import trace_lead
from database.models import (
    DataProvenance,
    EvidenceRecord,
    EvidenceType,
    Lead,
    LeadPriority,
    LeadStatus,
    VerificationStatus,
)

NOW = datetime(2026, 9, 8, 12, 0, 0)


def _real_lead_with_evidence(session):
    lead = Lead(company_name="Acme Tech", normalized_company_name="acme tech",
                lead_score=80.0, lead_priority=LeadPriority.HOT, status=LeadStatus.NEW,
                evidence_confidence=85, source_name="adzuna", source_url="https://adzuna/x",
                data_provenance=DataProvenance.REAL)
    session.add(lead)
    session.flush()
    session.add(EvidenceRecord(
        lead_id=lead.id, evidence_type=EvidenceType.JOB, content_hash="e1",
        source_name="adzuna", source_url="https://adzuna/x", observed_at=NOW,
        verification_status=VerificationStatus.VERIFIED, data_provenance=DataProvenance.REAL))
    session.flush()
    return lead


# --------------------------------------------------------------------------- #
# Provenance
# --------------------------------------------------------------------------- #
def test_provenance_clean_when_lead_has_evidence_and_source(seed_session):
    _real_lead_with_evidence(seed_session)
    report = provenance_report(seed_session)
    assert report["ok"] is True and report["total_failures"] == 0


def test_provenance_flags_lead_without_evidence(seed_session):
    seed_session.add(Lead(company_name="NoEv", lead_score=50, source_name="adzuna",
                          data_provenance=DataProvenance.REAL))
    seed_session.flush()
    report = provenance_report(seed_session)
    failing = {c["name"]: c["failures"] for c in report["checks"] if c["failures"] > 0}
    assert failing.get("leads_without_evidence", 0) == 1
    assert report["ok"] is False


def test_provenance_flags_lead_without_source(seed_session):
    seed_session.add(Lead(company_name="NoSrc", lead_score=50, data_provenance=DataProvenance.REAL))
    seed_session.flush()
    report = provenance_report(seed_session)
    failing = {c["name"]: c["failures"] for c in report["checks"] if c["failures"] > 0}
    assert failing.get("leads_without_source", 0) == 1


# --------------------------------------------------------------------------- #
# Synthetic data (DB — authoritative)
# --------------------------------------------------------------------------- #
def test_db_synthetic_clean_by_default(seed_session):
    _real_lead_with_evidence(seed_session)
    assert db_synthetic_report(seed_session)["ok"] is True


def test_db_synthetic_detects_synthetic_lead(seed_session):
    # A synthetic row can only exist by bypassing guards (test-only isolated DB).
    seed_session.add(Lead(company_name="Fake", data_provenance=DataProvenance.SYNTHETIC))
    seed_session.flush()
    report = db_synthetic_report(seed_session)
    assert report["ok"] is False and report["by_table"].get("leads") == 1


# --------------------------------------------------------------------------- #
# Go / No-Go
# --------------------------------------------------------------------------- #
def test_go_when_clean(seed_session):
    _real_lead_with_evidence(seed_session)
    result = go_no_go(seed_session)
    assert result["verdict"] == "GO" and result["blockers"] == []


def test_no_go_when_synthetic_present(seed_session):
    _real_lead_with_evidence(seed_session)
    seed_session.add(Lead(company_name="Fake", data_provenance=DataProvenance.SYNTHETIC))
    seed_session.flush()
    result = go_no_go(seed_session)
    assert result["verdict"] == "NO-GO"
    assert any("synthetic" in b.lower() for b in result["blockers"])


# --------------------------------------------------------------------------- #
# Quality scorecard honesty
# --------------------------------------------------------------------------- #
def test_quality_insufficient_data_on_empty_db(seed_session):
    q = quality_report(seed_session)
    assert q["jobs"]["pct_with_company"] == INSUFFICIENT
    assert q["leads"]["pct_with_evidence"] == INSUFFICIENT


def test_quality_real_percentages_with_data(seed_session):
    _real_lead_with_evidence(seed_session)
    q = quality_report(seed_session)
    assert q["leads"]["total_real"] == 1
    assert q["leads"]["pct_with_evidence"] == 100.0


# --------------------------------------------------------------------------- #
# Source inventory + scorecard + trace
# --------------------------------------------------------------------------- #
def test_source_inventory_reports_honest_states(seed_session):
    inv = source_inventory(seed_session)
    assert inv, "expected at least one registered source"
    for s in inv:
        assert s["implementation"] in ("IMPLEMENTED", "NOT_IMPLEMENTED")
        # Connection is NOT_CHECKED until a real health check runs (no inference).
        assert s["connection_status"] in (
            "NOT_CHECKED", "NOT_CONFIGURED", "CONFIGURED", "CONNECTED",
            "AUTHENTICATION_FAILED", "RATE_LIMITED", "TEMPORARILY_UNAVAILABLE", "DISABLED", "ERROR",
        )


def test_scorecard_counts_are_actual(seed_session):
    _real_lead_with_evidence(seed_session)
    card = real_data_scorecard(seed_session)
    assert card["production_leads"] == 1
    assert card["evidence_records"] == 1
    assert card["leads_with_evidence"] == "1/1"


def test_trace_lead_honest_when_empty(seed_session):
    result = trace_lead(seed_session)
    assert result["available"] is False
    assert "No real lead" in result["message"]


def test_trace_lead_returns_real_chain(seed_session):
    lead = _real_lead_with_evidence(seed_session)
    result = trace_lead(seed_session, lead_id=lead.id)
    assert result["available"] is True
    assert result["lead"]["company"] == "Acme Tech"
    assert result["evidence_count"] == 1
    assert result["evidence_chain"][0]["source_name"] == "adzuna"
