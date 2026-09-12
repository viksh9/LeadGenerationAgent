"""Public-intelligence orchestrator tests (Prompt 45).

Isolated DB (seed_session). Providers are in-test stubs returning canned normalized
records — no network. Verifies cross-source merge/dedup, source priority, field
provenance, trust, company-facts fill, caching, and no-fake behaviour.
"""

from __future__ import annotations

from datetime import timedelta

import pytest

from config import get_settings
from database.models import (
    Company,
    DataProvenance,
    DecisionMaker,
    EmailStatus,
    Lead,
    LeadPriority,
    LeadStatus,
    SignalType,
)
from enrichment.public_intelligence_service import (
    PUBLIC_SOURCE_TYPES,
    discover_public_intelligence_for_lead,
    get_public_pocs_for_lead,
)
from integrations.public_intelligence.base import PublicIntelligenceProvider
from integrations.public_intelligence.models import (
    MATCH_LIKELY,
    MATCH_UNKNOWN,
    MATCH_VERIFIED,
    CompanyContext,
    PublicCompanyFacts,
    PublicContact,
    PublicPerson,
)


class _Stub(PublicIntelligenceProvider):
    def __init__(self, name, *, label, stype, people=None, facts=None, status_error=False):
        self.name, self.source_label, self.source_type = name, label, stype
        self._people, self._facts, self._err = people or [], facts, status_error

    def discover_people(self, ctx, roles):
        if self._err:
            from integrations.public_intelligence.base import ProviderUnavailable
            raise ProviderUnavailable("boom")
        for p in self._people:
            p.source, p.source_label, p.source_type = self.name, self.source_label, self.source_type
        return self._people

    def discover_company(self, ctx):
        return self._facts


def _seed(session, *, name="Acme Corp", domain="acme.com"):
    session.add(Company(canonical_name=name, normalized_name=name.lower(),
                        primary_domain=domain, data_provenance=DataProvenance.REAL))
    lead = Lead(company_name=name, normalized_company_name=name.lower(), lead_score=80,
                lead_priority=LeadPriority.HOT, status=LeadStatus.NEW, signal_type=SignalType.HIRING,
                estimated_hiring=30, data_provenance=DataProvenance.REAL)
    session.add(lead)
    session.commit()
    return lead


def _official(**kw):
    return PublicPerson(company_match_status=MATCH_VERIFIED, is_current=True, **kw)


def test_official_person_persisted_with_trust(seed_session):
    lead = _seed(seed_session)
    official = _Stub("official_company", label="Official Company Website", stype="company_profile",
                     people=[_official(full_name="Jane Doe", job_title="VP Engineering",
                                       work_email="jane@acme.com", source_url="https://acme.com/team")])
    summ = discover_public_intelligence_for_lead(seed_session, lead, providers=[official])
    assert summ.status == "ENRICHED" and summ.persisted == 1
    poc = summ.pocs[0]
    assert poc.full_name == "Jane Doe" and poc.business_email == "jane@acme.com"
    assert poc.email_status == EmailStatus.VERIFIED_SOURCE
    assert poc.contact_source == "Official Company Website"
    assert poc.contact_trust_status == "VERIFIED"
    # official(35) + company(25) + title(20) + email(10) = 90
    assert poc.contact_trust_score == 90


def test_cross_source_merge_dedup_by_linkedin(seed_session):
    lead = _seed(seed_session)
    li = "https://linkedin.com/in/jane"
    official = _Stub("official_company", label="Official Company Website", stype="company_profile",
                     people=[_official(full_name="Jane Doe", job_title="VP Engineering",
                                       linkedin_url=li, source_url="https://acme.com/team")])
    github = _Stub("github", label="GitHub", stype="github_public_profile",
                   people=[PublicPerson(full_name="Jane Doe", job_title="VP Engineering",
                                        linkedin_url=li, work_email="jane@acme.com",
                                        company_match_status=MATCH_LIKELY,
                                        source_url="https://github.com/jane")])
    summ = discover_public_intelligence_for_lead(seed_session, lead, providers=[official, github])
    assert summ.persisted == 1   # merged, not duplicated
    poc = summ.pocs[0]
    # Higher-priority official source is canonical; github filled the email.
    assert poc.contact_source == "Official Company Website" and poc.business_email == "jane@acme.com"
    assert len(poc.source_references) >= 2   # both sources recorded (field provenance)


def test_unknown_match_not_persisted(seed_session):
    lead = _seed(seed_session)
    github = _Stub("github", label="GitHub", stype="github_public_profile",
                   people=[PublicPerson(full_name="Bob", job_title="VP Engineering",
                                        company_match_status=MATCH_UNKNOWN,
                                        source_url="https://github.com/bob")])
    summ = discover_public_intelligence_for_lead(seed_session, lead, providers=[github])
    assert summ.status == "NO_POC_FOUND" and summ.persisted == 0


def test_no_email_fabrication(seed_session):
    lead = _seed(seed_session)
    official = _Stub("official_company", label="Official Company Website", stype="company_profile",
                     people=[_official(full_name="No Email", job_title="CTO",
                                       source_url="https://acme.com/leadership")])
    poc = discover_public_intelligence_for_lead(seed_session, lead, providers=[official]).pocs[0]
    assert poc.business_email is None and poc.business_phone is None


def test_company_facts_filled_from_wikidata(seed_session):
    lead = _seed(seed_session, domain=None)
    facts = PublicCompanyFacts(website="https://acme.com", country="India", industry="IT",
                               wikidata_id="Q42", source="wikidata", source_url="https://www.wikidata.org/wiki/Q42")
    wd = _Stub("wikidata", label="Wikidata", stype="wikidata_entity", facts=facts)
    summ = discover_public_intelligence_for_lead(seed_session, lead, providers=[wd])
    assert set(summ.company_facts_updated) >= {"website", "wikidata_id", "industry", "headquarters_country"}
    co = seed_session.query(Company).first()
    assert co.wikidata_id == "Q42" and co.website == "https://acme.com" and co.headquarters_country == "India"


def test_company_facts_never_overwrite_existing(seed_session):
    lead = _seed(seed_session)
    co = seed_session.query(Company).first()
    co.website = "https://existing.example"
    seed_session.commit()
    facts = PublicCompanyFacts(website="https://acme.com", source="wikidata")
    summ = discover_public_intelligence_for_lead(seed_session, lead,
                                                 providers=[_Stub("wikidata", label="Wikidata",
                                                                  stype="wikidata_entity", facts=facts)])
    seed_session.refresh(co)
    assert co.website == "https://existing.example"   # not overwritten
    assert "website" not in summ.company_facts_updated


def test_provider_error_no_people(seed_session):
    lead = _seed(seed_session)
    summ = discover_public_intelligence_for_lead(seed_session, lead, providers=[
        _Stub("github", label="GitHub", stype="github_public_profile", status_error=True)])
    assert summ.provider_status["github"] in ("UNAVAILABLE", "ERROR")
    assert summ.persisted == 0 and summ.status == "NO_POC_FOUND"


def test_caching_reuses(seed_session):
    lead = _seed(seed_session)
    official = _Stub("official_company", label="Official Company Website", stype="company_profile",
                     people=[_official(full_name="Jane Doe", job_title="VP Engineering",
                                       source_url="https://acme.com/team")])
    discover_public_intelligence_for_lead(seed_session, lead, providers=[official])
    summ2 = discover_public_intelligence_for_lead(seed_session, lead, providers=[official])
    assert summ2.status == "CACHED" and len(summ2.pocs) == 1


def test_lead_score_unchanged(seed_session):
    lead = _seed(seed_session)
    before = lead.lead_score
    official = _Stub("official_company", label="Official Company Website", stype="company_profile",
                     people=[_official(full_name="Jane Doe", job_title="VP Engineering",
                                       source_url="https://acme.com/team")])
    discover_public_intelligence_for_lead(seed_session, lead, providers=[official])
    seed_session.refresh(lead)
    assert lead.lead_score == before
