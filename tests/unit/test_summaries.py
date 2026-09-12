"""Deterministic Signal + Company Profile summaries (Prompt 50, §14/§19). No DB."""

from __future__ import annotations

from database.models import Company, DataProvenance, Lead, LeadPriority, LeadStatus, SignalType
from intelligence.opportunity_view import derive_opportunity_view
from intelligence.summaries import build_company_profile, build_signal_summary


def _lead(**kw) -> Lead:
    base = dict(company_name="Acme Tech", normalized_company_name="acme tech", lead_score=80,
                lead_priority=LeadPriority.HOT, status=LeadStatus.NEW, signal_type=SignalType.HIRING,
                estimated_hiring=47, it_job_count=47, technologies=["Java", "AWS", "AI"],
                location="Bengaluru", industry="IT Services", data_provenance=DataProvenance.REAL)
    base.update(kw)
    return Lead(**base)


def test_signal_summary_uses_real_counts_and_tech():
    s = build_signal_summary(_lead())
    assert "47 open IT roles" in s
    assert "Java" in s and "AWS" in s


def test_signal_summary_empty_when_no_evidence():
    lead = _lead(estimated_hiring=0, it_job_count=0, recent_job_count=0, technologies=[], signal_type=None)
    assert build_signal_summary(lead) == ""


def test_signal_summary_singular_role():
    s = build_signal_summary(_lead(estimated_hiring=1, it_job_count=1))
    assert "1 open IT role" in s and "roles" not in s


def test_company_profile_india_presence_and_headline():
    lead = _lead()
    company = Company(canonical_name="Acme Tech", normalized_name="acme tech", industry="IT Services",
                      india_presence=True, full_address="Bengaluru, Karnataka",
                      careers_url="https://acme.com/careers", data_provenance=DataProvenance.REAL)
    ov = derive_opportunity_view(lead)
    profile = build_company_profile(lead, company, opportunity=ov, data_trust=82)
    assert profile.india_presence == "Yes"
    assert profile.data_trust == 82
    assert "Acme Tech" in profile.headline and "IT Services" in profile.headline
    assert profile.career_site == "https://acme.com/careers"


def test_company_profile_no_company_stays_unknown_and_blank():
    profile = build_company_profile(_lead(), None, data_trust=0)
    assert profile.india_presence == "UNKNOWN"
    assert profile.registered_location is None      # never invented
    assert profile.data_trust == 0
