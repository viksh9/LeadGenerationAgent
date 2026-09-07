"""Decision-maker / contact enrichment: role recommendation, official-source person
+ contact extraction, resolution/dedup, verification, outreach readiness, and APIs.

All offline: HTML is served via httpx.MockTransport; no external network, no
fabricated people. Enforces the no-guessing policy (no invented emails/URLs).
"""

from __future__ import annotations

import httpx
import pytest

import api.main
from api.dependencies import get_session
from collectors.company.config import load_career_config
from collectors.company.http_client import SafeHttpClient
from database.models import (
    Company, ContactType, DataProvenance, DecisionMaker, PersonMatchStatus,
    RoleCategory, SignalType, VerificationStatus,
)
from database.repository import create_lead
from enrichment.enrichment_service import enrich_company, resolve_person
from enrichment.outreach import OutreachInputs, classify_outreach_readiness
from enrichment.person_enricher import (
    OfficialCompanySourceEnricher, classify_role, extract_business_contacts, extract_people,
)
from enrichment.stakeholder import recommend_for_lead
from database.models import OutreachReadiness


def _client(html):
    return SafeHttpClient(load_career_config(), http=httpx.Client(
        transport=httpx.MockTransport(lambda r: httpx.Response(200, text=html,
                                                               headers={"content-type": "text/html"}))))


LEADERSHIP_HTML = '''
<script type="application/ld+json">{"@type":"Person","name":"Jane Doe","jobTitle":"Chief Technology Officer","url":"https://acme.example/team/jane"}</script>
<script type="application/ld+json">{"@type":"Organization","employee":[{"@type":"Person","name":"Ravi Kumar","jobTitle":"VP Engineering"}]}</script>
<a href="mailto:careers@acme.example">Careers</a>
<a href="mailto:procurement@acme.example">Procurement</a>
<a href="mailto:randomperson@gmail.com">personal</a>
'''


# --------------------------------------------------------------------------- #
# Role recommendation (opportunity-specific)
# --------------------------------------------------------------------------- #
def test_role_recommendation_for_hiring_ramp():
    from database.models import Lead
    lead = Lead(company_name="Acme", signal_type=SignalType.HIRING,
                technologies=["Java", "AWS"], estimated_hiring=25, industry="IT")
    result = recommend_for_lead(lead)
    roles = [r.role for r in result.recommended_roles]
    assert result.recommended_roles[0].is_primary
    assert any("Engineering" in r for r in roles)       # eng-leadership roles surface


def test_classify_role_maps_titles():
    assert classify_role("Chief Technology Officer")[0] == "CTO"
    assert classify_role("VP of Engineering")[1] is RoleCategory.ENGINEERING
    assert classify_role("Head of Procurement")[1] is RoleCategory.PROCUREMENT
    assert classify_role(None) == (None, RoleCategory.OTHER, None)


# --------------------------------------------------------------------------- #
# Official-source extraction (real, no fabrication)
# --------------------------------------------------------------------------- #
def test_extract_people_from_jsonld():
    people = extract_people(LEADERSHIP_HTML)
    names = {(p.full_name, p.job_title) for p in people}
    assert ("Jane Doe", "Chief Technology Officer") in names
    assert ("Ravi Kumar", "VP Engineering") in names


def test_extract_contacts_rejects_personal_and_keeps_business():
    contacts = extract_business_contacts(LEADERSHIP_HTML, company_domain="acme.example")
    emails = {c.value for c in contacts}
    assert "careers@acme.example" in emails
    assert "procurement@acme.example" in emails
    assert "randomperson@gmail.com" not in emails       # personal address rejected


def test_no_guessed_email_or_profile():
    # A page with a person name but NO email/profile must not fabricate either.
    html = '<script type="application/ld+json">{"@type":"Person","name":"Asha Rao","jobTitle":"Engineering Manager"}</script>'
    people = extract_people(html)
    assert people and people[0].profile_url is None      # no invented URL
    assert extract_business_contacts(html, company_domain="acme.example") == []  # no invented email


# --------------------------------------------------------------------------- #
# Persistence, resolution, verification, idempotency
# --------------------------------------------------------------------------- #
def _company(session):
    c = Company(canonical_name="Acme Technologies", normalized_name="acme technologies",
                primary_domain="acme.example", website="https://acme.example",
                data_provenance=DataProvenance.REAL)
    session.add(c); session.commit()
    return c


def test_enrichment_persists_real_records(seed_session):
    company = _company(seed_session)
    enricher = OfficialCompanySourceEnricher(client=_client(LEADERSHIP_HTML), max_pages=1)
    summary = enrich_company(seed_session, company, enricher=enricher)
    assert summary.people_accepted == 2 and summary.contacts_accepted == 2
    people = seed_session.query(DecisionMaker).filter(DecisionMaker.full_name.is_not(None)).all()
    jane = next(p for p in people if p.full_name == "Jane Doe")
    assert jane.normalized_role == "CTO"
    assert jane.data_provenance is DataProvenance.REAL
    assert jane.verification_status is VerificationStatus.VERIFIED
    assert jane.identity_confidence >= 80 and jane.evidence_confidence >= 80
    assert jane.source_url and jane.source_references                       # provenance present


def test_enrichment_idempotent(seed_session):
    company = _company(seed_session)
    enricher = OfficialCompanySourceEnricher(client=_client(LEADERSHIP_HTML), max_pages=1)
    enrich_company(seed_session, company, enricher=enricher)
    second = enrich_company(seed_session, company, enricher=enricher)
    assert second.people_accepted == 0 and second.duplicates >= 2           # upsert, no dupes
    assert seed_session.query(DecisionMaker).filter(DecisionMaker.full_name.is_not(None)).count() == 2


def test_person_resolution_no_name_only_merge(seed_session):
    company = _company(seed_session)
    enricher = OfficialCompanySourceEnricher(client=_client(LEADERSHIP_HTML), max_pages=1)
    enrich_company(seed_session, company, enricher=enricher)
    # Exact (company+name+role) resolves; same name + different role → REVIEW, not silent merge.
    _, exact = resolve_person(seed_session, company_id=company.id,
                              normalized_name="jane doe", normalized_role="CTO")
    assert exact is PersonMatchStatus.EXACT_MATCH
    _, diff = resolve_person(seed_session, company_id=company.id,
                             normalized_name="jane doe", normalized_role="CEO")
    assert diff is PersonMatchStatus.REVIEW_REQUIRED
    # Different company, same name → NO_MATCH (never merged across companies).
    _, other = resolve_person(seed_session, company_id=999, normalized_name="jane doe",
                              normalized_role="CTO")
    assert other is PersonMatchStatus.NO_MATCH


def test_enrichment_source_failure_no_fake_data(seed_session):
    company = _company(seed_session)
    failing = SafeHttpClient(load_career_config(), http=httpx.Client(
        transport=httpx.MockTransport(lambda r: httpx.Response(500))))
    enricher = OfficialCompanySourceEnricher(client=failing, max_pages=1)
    summary = enrich_company(seed_session, company, enricher=enricher)
    assert summary.people_accepted == 0 and summary.contacts_accepted == 0   # no fallback records
    assert seed_session.query(DecisionMaker).count() == 0


# --------------------------------------------------------------------------- #
# Outreach readiness (separate axis)
# --------------------------------------------------------------------------- #
def test_outreach_readiness_bands():
    assert classify_outreach_readiness(OutreachInputs(
        opportunity_verified=True, company_resolved=True, role_identified=True,
        has_verified_contact=True)).readiness is OutreachReadiness.READY
    assert classify_outreach_readiness(OutreachInputs(
        opportunity_verified=True, role_identified=True)).readiness is OutreachReadiness.ROLE_ONLY
    assert classify_outreach_readiness(OutreachInputs(
        evidence_stale=True)).readiness is OutreachReadiness.HOLD
    assert classify_outreach_readiness(OutreachInputs()).readiness is OutreachReadiness.RESEARCH_REQUIRED


# --------------------------------------------------------------------------- #
# APIs
# --------------------------------------------------------------------------- #
def test_contacts_api_empty(client):
    assert client.get("/contacts").json()["total"] == 0


def test_lead_stakeholders_roles_only(client):
    session = next(api.main.app.dependency_overrides[get_session]())
    lead = create_lead(session, company_name="Acme Technologies", signal_type=SignalType.HIRING,
                       technologies=["Java", "AWS"], estimated_hiring=20, industry="IT",
                       source_url="https://x/1", source_count=1)
    lid = lead.id
    session.close()
    body = client.get(f"/leads/{lid}/stakeholders").json()
    assert body["recommended_roles"]                        # roles present
    assert body["verified_decision_makers"] == []            # no verified person yet
    assert body["outreach_readiness"] in ("RESEARCH_REQUIRED", "ROLE_ONLY")


def test_enrich_endpoint_monkeypatched(client, monkeypatch):
    from types import SimpleNamespace
    fake_company = SimpleNamespace(id=5, canonical_name="Acme", primary_domain="acme.example",
                                   website="https://acme.example")
    monkeypatch.setattr("api.routes.contacts.company_repo.get_company",
                        lambda s, cid: fake_company if cid == 5 else None)
    monkeypatch.setattr("api.routes.contacts.enrich_company",
                        lambda s, c, provenance=None: SimpleNamespace(
                            provider="official_company", people_found=2, contacts_found=1,
                            people_accepted=2, contacts_accepted=1, duplicates=0,
                            pages_fetched=1, errors=[]))
    body = client.post("/companies/5/enrich").json()
    assert body["people_accepted"] == 2 and body["provider"] == "official_company"
    assert client.post("/companies/999/enrich").status_code == 404


def test_lead_stakeholders_404(client):
    assert client.get("/leads/99999/stakeholders").status_code == 404
