"""Unit tests for the deduplication matcher (identity.match) + similarity."""

from __future__ import annotations

from datetime import datetime

from database.models import MatchDecision, RemoteType
from processors.deduplication.identity import DedupRecord, match
from processors.deduplication.similarity import description_similarity, title_similarity


def rec(**kw) -> DedupRecord:
    ext = kw.get("external_id", "1")
    base = dict(
        source_id="adzuna", external_id="1", source_url=f"https://x/{ext}",
        normalized_company_name="abc technologies", company_domain=None,
        normalized_title="Senior Java Backend Engineer", original_title="Senior Java Backend Engineer",
        city="Bengaluru", state="Karnataka", country="India", remote_type=RemoteType.UNKNOWN,
        published_at=datetime(2026, 9, 3), description="Java Spring Boot AWS backend microservices",
        technologies=["Java", "AWS"], source_priority=2,
    )
    base.update(kw)
    return DedupRecord(**base)


def test_same_source_external_id():
    r = match(rec(source_id="adzuna", external_id="1"), rec(source_id="adzuna", external_id="1"))
    assert r.decision is MatchDecision.AUTO_MERGE and r.score == 100


def test_same_url():
    r = match(rec(external_id="1", source_url="https://ex.com/j"), rec(external_id="2", source_url="https://ex.com/j"))
    assert r.decision is MatchDecision.AUTO_MERGE and "source_url" in r.matched_fields


def test_company_title_location_merge():
    a = rec(source_id="company_career", external_id="c1", company_domain="abc.com")
    b = rec(source_id="adzuna", external_id="a1", normalized_title="Senior Java Backend Engineer")
    r = match(a, b)
    assert r.decision is MatchDecision.AUTO_MERGE
    assert "normalized_company_name" in r.matched_fields and "city" in r.matched_fields


def test_title_variation_still_matches_when_normalized_equal():
    # "Sr." and "Senior" both normalize to the same title upstream.
    r = match(rec(source_id="adzuna", external_id="a1", normalized_title="Senior Java Developer"),
              rec(source_id="company_career", external_id="b1", normalized_title="Senior Java Developer"))
    assert r.decision is MatchDecision.AUTO_MERGE


def test_different_city_not_merged():
    r = match(rec(source_id="adzuna", external_id="a1", city="Bengaluru"), rec(source_id="company_career", external_id="b1", city="Pune"))
    assert r.decision is MatchDecision.NO_MATCH
    assert any("city" in d for d in r.differences)


def test_different_company_not_merged():
    r = match(rec(source_id="adzuna", normalized_company_name="abc technologies"),
              rec(source_id="company_career", normalized_company_name="xyz digital", external_id="z1"))
    assert r.decision is MatchDecision.NO_MATCH


def test_different_project_not_merged():
    a = rec(source_id="adzuna", external_id="p1", normalized_title="Senior Java Backend Engineer - Payments Platform",
            description="payments settlement ledger reconciliation")
    b = rec(source_id="company_career", external_id="c1", normalized_title="Senior Java Backend Engineer - Cloud Platform",
            description="kubernetes infra platform tooling")
    r = match(a, b)
    assert r.decision is MatchDecision.NO_MATCH
    assert any("project" in d or "team" in d for d in r.differences)


def test_remote_matches_across_sources_without_city():
    a = rec(source_id="adzuna", external_id="a1", city=None, remote_type=RemoteType.REMOTE)
    b = rec(source_id="company_career", external_id="b1", city=None, remote_type=RemoteType.REMOTE)
    r = match(a, b)
    assert r.decision is MatchDecision.AUTO_MERGE and "remote" in r.matched_fields


def test_match_explanation_present():
    r = match(rec(source_id="company_career", external_id="c1"), rec(source_id="adzuna", external_id="a1"))
    assert r.reason and r.matched_fields


def test_similarity_helpers():
    assert title_similarity("Senior Java Developer", "Senior Java Developer") == 1.0
    assert description_similarity("java spring aws", "java spring aws") == 1.0
    assert description_similarity("payments ledger", "kubernetes infra") < 0.3
