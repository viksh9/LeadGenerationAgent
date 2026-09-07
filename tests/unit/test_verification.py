"""Unit tests for the evidence verification engine (§21 scenarios)."""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from database.models import (
    ConflictSeverity,
    LeadReadiness,
    SourceTier,
    VerificationStatus,
)
from verification.conflicts import ConflictEvidence, detect_conflicts
from verification.corroboration import EvidenceItem, corroborate
from verification.freshness import compute_freshness
from verification.lead_readiness import classify_readiness
from verification.signal_verification import EvidenceInput, verify_evidence_set
from verification.source_reliability import compute_source_reliability, source_tier_for

NOW = datetime(2026, 9, 5)


# --- Source reliability ---------------------------------------------------- #
def test_source_reliability_tiers():
    official = compute_source_reliability("company_career_pages")
    aggregator = compute_source_reliability("adzuna")
    unknown = compute_source_reliability("some_random_source")
    assert official.source_tier is SourceTier.TIER_1
    assert official.reliability_score > aggregator.reliability_score > unknown.reliability_score
    assert unknown.source_tier is SourceTier.TIER_4


def test_source_tier_by_category_fallback():
    assert source_tier_for("unconfigured", "GOVERNMENT") is SourceTier.TIER_1
    assert source_tier_for("unconfigured", "NEWS") is SourceTier.TIER_3


# --- Freshness ------------------------------------------------------------- #
def test_freshness_current_vs_old():
    fresh = compute_freshness(signal_type="HIRING", published_at=NOW - timedelta(days=2), now=NOW)
    old = compute_freshness(signal_type="HIRING", published_at=NOW - timedelta(days=200), now=NOW)
    assert fresh.score > 80 and not fresh.is_stale
    assert old.is_stale and old.score < 30


def test_expired_job_is_stale():
    r = compute_freshness(signal_type="HIRING", published_at=NOW - timedelta(days=5), source_status="closed", now=NOW)
    assert r.is_stale


def test_expired_tender_is_stale():
    r = compute_freshness(signal_type="TENDER", published_at=NOW - timedelta(days=3),
                          closing_date=NOW - timedelta(days=1), now=NOW)
    assert r.is_stale


# --- Corroboration (syndication) ------------------------------------------- #
def test_syndicated_not_independent():
    items = [
        EvidenceItem("company_career", SourceTier.TIER_1, content_hash="job-1"),
        EvidenceItem("adzuna", SourceTier.TIER_2, content_hash="job-1"),        # syndicated copy
        EvidenceItem("rss_news", SourceTier.TIER_3, content_hash="job-1"),      # syndicated copy
    ]
    result = corroborate(items)
    assert result.independent_support_count == 1     # NOT 3
    assert result.syndicated_count == 2


def test_independent_sources_corroborate():
    items = [
        EvidenceItem("company_career", SourceTier.TIER_1, content_hash="a"),
        EvidenceItem("government_open_data", SourceTier.TIER_1, content_hash="b"),
    ]
    result = corroborate(items)
    assert result.independent_support_count == 2
    assert result.corroboration_score > 0


# --- Conflicts ------------------------------------------------------------- #
def test_active_vs_closed_conflict():
    items = [
        ConflictEvidence(0, "company_career", SourceTier.TIER_1, status="active"),
        ConflictEvidence(1, "rss_news", SourceTier.TIER_3, status="expired"),
    ]
    findings = detect_conflicts(items)
    assert findings and findings[0].severity is ConflictSeverity.HIGH
    assert findings[0].preferred_index == 0   # authoritative source preferred


# --- Verification statuses ------------------------------------------------- #
def _ev(source, ch="j1", days=3, status=None, url="https://x/1"):
    return EvidenceInput(source_id=source, content_hash=ch, source_url=url,
                         published_at=NOW - timedelta(days=days), status=status)


def test_status_verified():
    r = verify_evidence_set([_ev("company_career_pages")], signal_type="HIRING", now=NOW)
    assert r.verification_status is VerificationStatus.VERIFIED
    assert r.source_reliability >= 90 and r.freshness_score >= 80


def test_status_unverified_weak_source():
    r = verify_evidence_set([_ev("some_unknown_source")], signal_type="HIRING", now=NOW)
    assert r.verification_status in (VerificationStatus.UNVERIFIED, VerificationStatus.PARTIALLY_VERIFIED)
    assert r.source_reliability < 40


def test_status_stale_old_evidence():
    r = verify_evidence_set([_ev("company_career_pages", days=200)], signal_type="HIRING", now=NOW)
    assert r.verification_status is VerificationStatus.STALE


def test_status_contradicted():
    r = verify_evidence_set(
        [_ev("company_career_pages", ch="a", status="active"),
         _ev("rss_news", ch="b", status="expired")],
        signal_type="HIRING", now=NOW)
    assert r.verification_status is VerificationStatus.CONTRADICTED


def test_scores_are_distinct():
    # A verified lead can still have reliability != evidence_confidence != freshness.
    r = verify_evidence_set([_ev("adzuna")], signal_type="HIRING", now=NOW)
    assert r.source_reliability != r.evidence_confidence or r.freshness_score != r.evidence_confidence


def test_syndication_does_not_inflate_independent_support():
    r = verify_evidence_set(
        [_ev("company_career_pages", ch="job-1", url="https://a/1"),
         _ev("adzuna", ch="job-1", url="https://b/1"),
         _ev("rss_news", ch="job-1", url="https://c/1")],
        signal_type="HIRING", now=NOW)
    assert r.independent_support_count == 1   # 3 URLs, 1 underlying job
    assert r.syndicated_count == 2


# --- Lead readiness -------------------------------------------------------- #
@pytest.mark.parametrize("status,ec,fresh,signal,expected", [
    (VerificationStatus.VERIFIED, 80, 80, True, LeadReadiness.READY),
    (VerificationStatus.PARTIALLY_VERIFIED, 50, 60, True, LeadReadiness.REVIEW_REQUIRED),
    (VerificationStatus.STALE, 60, 20, True, LeadReadiness.HOLD),
    (VerificationStatus.CONTRADICTED, 60, 60, True, LeadReadiness.HOLD),
    (VerificationStatus.UNVERIFIED, 20, 30, False, LeadReadiness.DISCARD),
])
def test_lead_readiness(status, ec, fresh, signal, expected):
    assert classify_readiness(verification_status=status, evidence_confidence=ec,
                              freshness_score=fresh, has_meaningful_signal=signal) is expected
