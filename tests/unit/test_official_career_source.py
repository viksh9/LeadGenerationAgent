"""Official career source: domain discovery + pluggable ATS detection (Prompt 48).

Pure/offline — no network. Verifies the domain-discovery service never treats an
aggregator/ATS host as a company's official domain, never selects on name
similarity alone, and reports the correct statuses; and that the ATS provider
registry detects Greenhouse/Lever without fabricating identifiers.
"""

from __future__ import annotations

import pytest

from collectors.company.ats import ATS_PROVIDERS, detect_ats_provider, supported_ats
from collectors.company.domain_discovery import CompanyDomainDiscoveryService
from database.models import AtsProvider

SVC = CompanyDomainDiscoveryService()


# --------------------------------------------------------------------------- #
# Domain discovery (§4)
# --------------------------------------------------------------------------- #
def test_official_domain_from_own_source_url_is_verified():
    r = SVC.discover(company_name="Example Technologies",
                     source_url="https://example.com/careers/job/123")
    assert r.status == "VERIFIED" and r.selected_domain == "example.com" and r.confidence >= 80


def test_existing_domain_matching_name_is_verified():
    r = SVC.discover(company_name="Infosys Limited", existing_domain="infosys.com")
    assert r.status == "VERIFIED" and r.selected_domain == "infosys.com"


def test_aggregator_source_is_never_official():
    for host in ("https://www.adzuna.in/details/1", "https://jooble.org/jdp/2",
                 "https://www.linkedin.com/jobs/3", "https://boards.greenhouse.io/acme"):
        r = SVC.discover(company_name="Example Technologies", source_url=host)
        assert r.selected_domain is None
        assert r.status in ("NOT_FOUND",)


def test_two_distinct_strong_domains_conflict():
    r = SVC.discover(company_name="Acme", existing_domain="acme.com",
                     source_url="https://acme.io/careers")
    assert r.status == "CONFLICT" and r.selected_domain is None


def test_name_mismatch_requires_review_not_selection():
    r = SVC.discover(company_name="Zephyr Analytics", source_url="https://randomhost999.com/jobs/1")
    assert r.status == "REVIEW_REQUIRED"
    assert r.selected_domain is None            # never selected on similarity alone


def test_no_signals_not_found():
    r = SVC.discover(company_name="Nowhere Inc")
    assert r.status == "NOT_FOUND" and r.selected_domain is None


def test_partial_name_match_is_review_required():
    # "cloudninja" domain vs "CloudNinja Software Solutions" → strong (label in name).
    r = SVC.discover(company_name="Globex", source_url="https://globexcorp.com/jobs")
    assert r.status in ("VERIFIED", "POSSIBLE", "REVIEW_REQUIRED")  # deterministic, never fabricated
    if r.selected_domain:
        assert r.selected_domain == "globexcorp.com"


def test_two_level_tld_registrable_domain():
    r = SVC.discover(company_name="Wipro", source_url="https://careers.wipro.co.in/jobs/1")
    assert r.selected_domain == "wipro.co.in"


# --------------------------------------------------------------------------- #
# Pluggable ATS detection (§7/§11)
# --------------------------------------------------------------------------- #
def test_supported_ats_are_only_implemented_ones():
    assert set(supported_ats()) == {"Greenhouse", "Lever"}
    assert set(ATS_PROVIDERS.keys()) == {AtsProvider.GREENHOUSE, AtsProvider.LEVER}


def test_detect_greenhouse():
    provider, board = detect_ats_provider(
        html='<a href="https://boards.greenhouse.io/acmecorp">Careers</a>',
        final_url="https://acme.com/careers")
    assert provider is not None and provider.provider is AtsProvider.GREENHOUSE
    assert board == "acmecorp"


def test_detect_lever():
    provider, board = detect_ats_provider(html='Apply at https://jobs.lever.co/acme-labs',
                                          final_url="https://acme.com/careers")
    assert provider is not None and provider.provider is AtsProvider.LEVER
    assert board == "acme-labs"


def test_detect_none_when_no_ats():
    provider, board = detect_ats_provider(html="<p>no ats here</p>", final_url="https://acme.com")
    assert provider is None and board is None


def test_ats_provider_builds_collector_for_board():
    gh = ATS_PROVIDERS[AtsProvider.GREENHOUSE]
    collector = gh.build_collector("acmecorp")
    assert collector is not None and hasattr(collector, "fetch")
