"""Lead Intelligence aggregator (Prompt 50, §1/§43). Isolated seed_session DB.

Verifies company-level (not per-job) POC aggregation, primary/secondary ranking by
role match, derived POC status, distinct Data/Contact trust, contributing-source-only
listing, recommended-role-only fallback (no person => no fabrication), and that AI
highlights are deterministic + honestly unavailable when no AI provider is configured.
"""

from __future__ import annotations

from database.models import (
    Company,
    CompanyFieldEvidence,
    ContactType,
    DataProvenance,
    DecisionMaker,
    EmailStatus,
    Lead,
    LeadPriority,
    LeadStatus,
    PersonMatchStatus,
    SignalType,
    VerificationStatus,
    utcnow,
)
from intelligence.lead_intelligence import build_lead_intelligence, lead_sources

NOW = utcnow()


def _seed_company_lead(session, *, data_trust=82):
    session.add(Company(canonical_name="Acme Tech", normalized_name="acme tech", primary_domain="acme.com",
                        industry="IT Services", india_presence=True, full_address="Bengaluru, Karnataka",
                        careers_url="https://acme.com/careers", data_trust_score=data_trust,
                        data_provenance=DataProvenance.REAL))
    lead = Lead(company_name="Acme Tech", normalized_company_name="acme tech", lead_score=85,
                lead_priority=LeadPriority.HOT, status=LeadStatus.NEW, signal_type=SignalType.HIRING,
                estimated_hiring=47, it_job_count=47, technologies=["Java", "AWS"], location="Bengaluru",
                source_name="Official Career Site", source_url="https://acme.com/careers",
                data_provenance=DataProvenance.REAL)
    session.add(lead)
    session.flush()
    company = session.query(Company).first()
    session.add(CompanyFieldEvidence(company_id=company.id, field="website_url", value="https://acme.com",
                                     source="Official Company Website", source_type="company_website",
                                     source_url="https://acme.com", source_priority=1, trust_score=100,
                                     data_provenance=DataProvenance.REAL, retrieved_at=NOW))
    session.commit()
    return lead, company


def _person(session, company, *, name, role, rms, trust, source="Apollo", employment="CURRENT_LIKELY",
            verification=VerificationStatus.PARTIALLY_VERIFIED, is_current=True, email=None):
    session.add(DecisionMaker(
        company_id=company.id, company_name=company.canonical_name, full_name=name,
        normalized_name=name.lower(), normalized_role=role.lower(), job_title=role,
        role_match_score=rms, match_score=rms, contact_trust_score=trust,
        contact_trust_status=("VERIFIED" if trust >= 80 else "LIKELY"), employment_status=employment,
        is_current=is_current, business_email=email, contact_type=ContactType.BUSINESS_EMAIL,
        email_status=EmailStatus.UNVERIFIED_SOURCE, verification_status=verification,
        match_status=PersonMatchStatus.POSSIBLE_MATCH, contact_source=source, source_type="contact_enrichment",
        freshness_score=95, last_verified_at=NOW, last_seen_at=NOW, data_provenance=DataProvenance.REAL))
    session.commit()


def test_ranks_primary_and_secondary_by_role_match(seed_session):
    lead, company = _seed_company_lead(seed_session)
    _person(seed_session, company, name="Bob Rep", role="Sales Rep", rms=40, trust=30, source="Lusha")
    _person(seed_session, company, name="Jane Doe", role="VP Engineering", rms=92, trust=70)
    intel = build_lead_intelligence(seed_session, lead, now=NOW)
    assert intel.primary_poc is not None
    assert intel.primary_poc.poc.full_name == "Jane Doe"
    assert intel.primary_poc.role_match_score == 92
    assert intel.secondary_pocs and intel.secondary_pocs[0].poc.full_name == "Bob Rep"


def test_distinct_trust_axes_and_poc_status(seed_session):
    lead, company = _seed_company_lead(seed_session, data_trust=82)
    _person(seed_session, company, name="Jane Doe", role="VP Engineering", rms=92, trust=70)
    intel = build_lead_intelligence(seed_session, lead, now=NOW)
    assert intel.data_trust == 82                    # company evidence quality
    assert intel.contact_trust == 70                 # contact match reliability (distinct)
    assert intel.lead_score == 85                    # commercial priority (distinct)
    assert intel.primary_poc.poc_status == "LIKELY"


def test_former_person_status(seed_session):
    lead, company = _seed_company_lead(seed_session)
    _person(seed_session, company, name="Old Cto", role="CTO", rms=88, trust=60, is_current=False)
    intel = build_lead_intelligence(seed_session, lead, now=NOW)
    assert intel.primary_poc.poc_status == "FORMER"


def test_recommended_role_only_when_no_person(seed_session):
    lead, _company = _seed_company_lead(seed_session)
    intel = build_lead_intelligence(seed_session, lead, now=NOW)
    assert intel.primary_poc is None                 # never fabricated
    assert intel.recommended_roles                   # roles offered instead
    assert intel.contact_trust == 0


def test_sources_only_contributing(seed_session):
    lead, company = _seed_company_lead(seed_session)
    _person(seed_session, company, name="Jane Doe", role="VP Engineering", rms=92, trust=70, source="Apollo")
    srcs = {s.source for s in lead_sources(seed_session, lead)}
    # Only sources that actually contributed — official website evidence, the signal
    # source, and the POC's provider. NOT every configured provider.
    assert "Official Company Website" in srcs
    assert "Official Career Site" in srcs
    assert "Apollo" in srcs
    assert "Hunter" not in srcs and "Prospeo" not in srcs


def test_ai_highlights_deterministic_and_unavailable_without_provider(seed_session):
    lead, company = _seed_company_lead(seed_session)
    _person(seed_session, company, name="Jane Doe", role="VP Engineering", rms=92, trust=70)
    intel = build_lead_intelligence(seed_session, lead, now=NOW)
    titles = [h.highlight_title for h in intel.ai_highlights.highlights]
    assert "Hiring Trend" in titles and "Technology Focus" in titles
    assert intel.ai_highlights.ai_available is False       # no AI provider configured in tests
    assert intel.ai_highlights.ai_insight is None
    assert intel.signal_summary and "47" in intel.signal_summary


def test_sales_action_is_evidence_based(seed_session):
    lead, company = _seed_company_lead(seed_session)
    _person(seed_session, company, name="Jane Doe", role="VP Engineering", rms=92, trust=70)
    intel = build_lead_intelligence(seed_session, lead, now=NOW)
    assert "VP Engineering" in intel.sales_action
    assert "need" not in intel.sales_action.lower() or "capacity" in intel.sales_action.lower()
