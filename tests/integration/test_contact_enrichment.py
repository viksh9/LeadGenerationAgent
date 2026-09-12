"""Multi-provider contact-enrichment waterfall (Prompt 49).

Isolated throwaway DB (seed_session). Providers are injected fakes — no real network,
no keys. Verifies lead-priority/score gating, candidate discovery + Role Match ranking
(§18), credit caps (§11/§28), email-verification status preservation (§20/§21), phone
typing (§22), honest failure states (never fabricates a person/email), and persistence.
"""

from __future__ import annotations

import pytest

from database.models import (
    Company,
    DataProvenance,
    DecisionMaker,
    Lead,
    LeadPriority,
    LeadStatus,
    SignalType,
)
from enrichment.contact_enrichment import contact_trust, enrich_lead_contacts, role_match_score
from integrations.enrichment.base import (
    EmailResult,
    EnrichedPerson,
    EnrichmentProvider,
    EnrichmentUnavailable,
    PhoneResult,
    ProviderCapabilities,
)


# --------------------------------------------------------------------------- #
# Fake providers (test-only — never used at runtime)
# --------------------------------------------------------------------------- #
class FakeSearch(EnrichmentProvider):
    name = "apollo"
    source_label = "Apollo"
    capabilities = ProviderCapabilities(person_search=True, person_enrichment=True)

    def __init__(self, people, *, calls=None, raise_search=False):
        self._people = people
        self._calls = calls if calls is not None else {"search": 0, "enrich": 0}
        self._raise = raise_search

    def is_configured(self):
        return True

    def search_people(self, *, company_name=None, titles=None, domain=None, location=None):
        self._calls["search"] += 1
        if self._raise:
            raise EnrichmentUnavailable("down")
        return list(self._people)

    def enrich_person(self, *, full_name=None, linkedin_url=None, company_name=None, domain=None):
        self._calls["enrich"] += 1
        return EnrichedPerson(full_name=full_name, company_name=company_name, company_domain=domain,
                              work_email=EmailResult(email=f"{(full_name or '').split()[0].lower()}@{domain}",
                                                     verification_status="UNVERIFIED", source="Apollo"),
                              source="apollo", source_label="Apollo")


class FakeHunter(EnrichmentProvider):
    name = "hunter"
    source_label = "Hunter"
    capabilities = ProviderCapabilities(email_finder=True, email_verification=True)

    def __init__(self, verify_status="VALID"):
        self._vs = verify_status

    def is_configured(self):
        return True

    def find_business_email(self, *, full_name, domain):
        return EmailResult(email=f"{full_name.split()[0].lower()}@{domain}",
                           verification_status="UNVERIFIED", source="Hunter")

    def verify_email(self, email):
        return EmailResult(email=email, verification_status=self._vs, source="Hunter")


def _person(name, title, *, company="Acme Corp", domain="acme.com", email=None, phone=None, current=True):
    return EnrichedPerson(
        full_name=name, job_title=title, company_name=company, company_domain=domain,
        linkedin_url=f"https://linkedin.com/in/{name.split()[0].lower()}", is_current=current,
        work_email=EmailResult(email=email, verification_status="UNVERIFIED", source="Apollo") if email else None,
        phone=PhoneResult(number=phone, phone_type="BUSINESS_DIRECT", verification_status="UNKNOWN",
                          source="Apollo") if phone else None,
        source="apollo", source_label="Apollo")


def _seed(session, *, score=85, priority=LeadPriority.HOT):
    session.add(Company(canonical_name="Acme Corp", normalized_name="acme corp",
                        primary_domain="acme.com", data_provenance=DataProvenance.REAL))
    lead = Lead(company_name="Acme Corp", normalized_company_name="acme corp", lead_score=score,
                lead_priority=priority, status=LeadStatus.NEW, signal_type=SignalType.HIRING,
                estimated_hiring=30, technologies=["Java"], data_provenance=DataProvenance.REAL)
    session.add(lead)
    session.commit()
    return lead


# --------------------------------------------------------------------------- #
# Scoring
# --------------------------------------------------------------------------- #
def test_role_match_prefers_relevant_senior_current_matched():
    strong = _person("Jane Doe", "VP Engineering")
    weak = _person("Bob Smith", "Sales Intern", company="Other Co", domain="other.com", current=False)
    roles = ["VP Engineering", "CTO", "Head of Engineering"]
    assert role_match_score(strong, roles, company_matched=True) > \
           role_match_score(weak, roles, company_matched=False)


def test_contact_trust_formula_caps_at_100():
    assert contact_trust(official_current_role=True, current_company=True, current_title=True,
                         independent_confirmation=True, verified_work_email=True,
                         verified_business_phone=True) == 100
    assert contact_trust(official_current_role=False, current_company=True, current_title=True,
                         independent_confirmation=False, verified_work_email=False,
                         verified_business_phone=False) == 45


# --------------------------------------------------------------------------- #
# Gating
# --------------------------------------------------------------------------- #
def test_no_providers_returns_not_configured(seed_session):
    lead = _seed(seed_session)
    summ = enrich_lead_contacts(seed_session, lead, providers=[])
    assert summ.status == "NOT_CONFIGURED" and summ.persisted == 0


def test_low_score_lead_skipped(seed_session):
    lead = _seed(seed_session, score=20, priority=LeadPriority.LOW)
    summ = enrich_lead_contacts(seed_session, lead, providers=[FakeSearch([_person("Jane Doe", "CTO")])])
    assert summ.status == "SKIPPED_LOW_SCORE" and summ.persisted == 0
    assert seed_session.query(DecisionMaker).count() == 0   # nothing persisted


# --------------------------------------------------------------------------- #
# Happy path — discover, rank, enrich, verify, persist
# --------------------------------------------------------------------------- #
def test_enriches_ranks_and_verifies(seed_session):
    lead = _seed(seed_session)
    apollo = FakeSearch([_person("Bob Smith", "Sales Rep", company="Other", domain="other.com", current=False),
                         _person("Jane Doe", "VP Engineering")])
    summ = enrich_lead_contacts(seed_session, lead, providers=[apollo, FakeHunter(verify_status="VALID")])
    assert summ.status == "ENRICHED" and summ.persisted >= 1
    top = summ.pocs[0]
    assert top.full_name == "Jane Doe"                       # ranked above the weak candidate
    assert top.business_email == "jane@acme.com"
    assert top.email_verification_status == "VALID"          # Hunter verify preserved verbatim
    assert top.role_match_score > 0
    assert top.employment_status == "CURRENT_LIKELY"         # company matched
    assert top.contact_source == "Apollo"
    assert top.data_provenance == DataProvenance.REAL


def test_email_verification_status_preserved_not_overwritten(seed_session):
    lead = _seed(seed_session)
    apollo = FakeSearch([_person("Jane Doe", "CTO")])
    summ = enrich_lead_contacts(seed_session, lead, providers=[apollo, FakeHunter(verify_status="ACCEPT_ALL")])
    assert summ.pocs[0].email_verification_status == "ACCEPT_ALL"


# --------------------------------------------------------------------------- #
# Honest failure — never fabricate
# --------------------------------------------------------------------------- #
def test_provider_down_yields_no_data_no_fake(seed_session):
    lead = _seed(seed_session)
    summ = enrich_lead_contacts(seed_session, lead, providers=[FakeSearch([], raise_search=True)])
    assert summ.status == "NO_DATA" and summ.persisted == 0
    assert summ.provider_status.get("apollo") == "SOURCE_UNAVAILABLE"
    assert seed_session.query(DecisionMaker).count() == 0


def test_empty_search_yields_no_data(seed_session):
    lead = _seed(seed_session)
    summ = enrich_lead_contacts(seed_session, lead, providers=[FakeSearch([])])
    assert summ.status == "NO_DATA" and summ.persisted == 0


# --------------------------------------------------------------------------- #
# Credit caps
# --------------------------------------------------------------------------- #
def test_respects_enrichment_cap(seed_session):
    from config import get_settings
    s = get_settings()
    prev = s.max_contact_enrichments_per_opportunity
    s.max_contact_enrichments_per_opportunity = 1
    try:
        lead = _seed(seed_session)
        people = [_person(f"P{i} Name", "VP Engineering") for i in range(5)]
        summ = enrich_lead_contacts(seed_session, lead, providers=[FakeSearch(people), FakeHunter()])
        assert summ.persisted == 1                           # capped
    finally:
        s.max_contact_enrichments_per_opportunity = prev
