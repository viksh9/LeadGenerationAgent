"""Unit tests for company name normalization + entity resolution (§31/§32)."""

from __future__ import annotations

from company.classification import classify_company
from company.normalization import normalize_domain, normalize_name
from company.resolver import CompanyCandidate, CompanyEntityResolver, ObservedCompany
from database.models import CompanyMatchStatus, CompanyType

R = CompanyEntityResolver()


def _abc() -> CompanyCandidate:
    return CompanyCandidate(id=1, normalized_name="abc technologies", primary_domain="abc.com",
                            headquarters_city="Bengaluru", tokens=["abc"])


# --- Normalization --------------------------------------------------------- #
def test_name_normalization_and_legal_suffix():
    n = normalize_name("ABC Technologies Pvt. Ltd.")
    assert n.original_name == "ABC Technologies Pvt. Ltd."   # preserved
    assert n.normalized_name == "abc technologies"           # suffix stripped, not "abc"
    assert "pvt" not in n.legal_suffix_removed_name and "ltd" not in n.legal_suffix_removed_name


def test_domain_normalization():
    assert normalize_domain("https://www.abc.com/careers") == "abc.com"
    assert normalize_domain("http://abc.com/") == "abc.com"


# --- Resolution scenarios -------------------------------------------------- #
def test_scenario_a_same_domain_variant_exact_match():
    r = R.resolve(ObservedCompany(name="ABC Technologies Pvt Ltd", domain="https://www.abc.com/careers"), [_abc()])
    assert r.match_status is CompanyMatchStatus.EXACT_MATCH
    assert r.recommended_action == "LINK" and r.matched_company_id == 1
    assert "exact verified domain match" in r.matching_factors


def test_scenario_b_different_name_and_domain_no_merge():
    r = R.resolve(ObservedCompany(name="ABC Technology Solutions", domain="abctechnology.co.in"), [_abc()])
    assert r.match_status is CompanyMatchStatus.NO_MATCH
    assert r.recommended_action == "CREATE_NEW"


def test_scenario_f_same_name_different_domain_review():
    r = R.resolve(ObservedCompany(name="ABC Technologies", domain="abc-tech.in", city="Pune"), [_abc()])
    assert r.match_status is CompanyMatchStatus.CONFLICT
    assert r.recommended_action == "REVIEW" and r.matched_company_id is None
    assert r.conflicting_factors


def test_name_only_never_auto_links():
    r = R.resolve(ObservedCompany(name="ABC Technologies"), [_abc()])
    assert r.recommended_action != "LINK"   # name alone is never a confident merge


def test_high_confidence_via_domain_with_slightly_different_name():
    r = R.resolve(ObservedCompany(name="ABC Tech", domain="abc.com"), [_abc()])
    assert r.match_status is CompanyMatchStatus.EXACT_MATCH   # domain wins


def test_no_candidates_creates_new():
    r = R.resolve(ObservedCompany(name="New Co", domain="newco.com"), [])
    assert r.match_status is CompanyMatchStatus.NO_MATCH and r.recommended_action == "CREATE_NEW"


def test_explanation_is_present():
    r = R.resolve(ObservedCompany(name="ABC Technologies", domain="abc.com"), [_abc()])
    assert r.resolution_explanation and r.matching_factors


# --- Classification -------------------------------------------------------- #
def test_classification_requires_evidence():
    weak = classify_company(industry_text=None, technologies=[], job_count=1)
    assert weak.confidence < 40   # a lone job is not strong IT evidence
    strong = classify_company(industry_text="Cloud Services", technologies=["AWS", "Kubernetes"], job_count=10)
    assert strong.company_type is CompanyType.CLOUD and strong.confidence >= 70


def test_classification_fintech():
    r = classify_company(industry_text="FinTech Technology", technologies=["Java"], job_count=5)
    assert r.company_type is CompanyType.FINTECH_TECH
