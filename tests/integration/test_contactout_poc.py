"""Company-level POC discovery/enrichment service (Prompt 44).

Isolated throwaway DB (seed_session). ContactOut is stubbed with httpx.MockTransport
via an injected client — no real network, no token needed. Verifies company-level
(not per-job) discovery, company-match validation, no fabrication, provenance,
caching, credit control, dedup, and honest failure states.
"""

from __future__ import annotations

from datetime import timedelta

import httpx
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
from enrichment.contactout_poc import discover_pocs_for_lead, enrich_poc, get_pocs_for_lead
from integrations.contactout import ContactOutClient, ContactOutConfig


@pytest.fixture(autouse=True)
def _configure_contactout():
    s = get_settings()
    prev = (s.contactout_api_token, s.contactout_cache_ttl_hours,
            s.contactout_max_poc_searches_per_opportunity, s.contactout_max_enrichments_per_opportunity)
    s.contactout_api_token = "test-token"
    s.contactout_cache_ttl_hours = 168
    s.contactout_max_poc_searches_per_opportunity = 3
    s.contactout_max_enrichments_per_opportunity = 2
    yield s
    (s.contactout_api_token, s.contactout_cache_ttl_hours,
     s.contactout_max_poc_searches_per_opportunity, s.contactout_max_enrichments_per_opportunity) = prev


def _seed(session, *, name="Acme Corp", domain="acme.com"):
    session.add(Company(canonical_name=name, normalized_name=name.lower(),
                        primary_domain=domain, data_provenance=DataProvenance.REAL))
    lead = Lead(company_name=name, normalized_company_name=name.lower(), lead_score=80,
                lead_priority=LeadPriority.HOT, status=LeadStatus.NEW, signal_type=SignalType.HIRING,
                estimated_hiring=30, technologies=["Java"], data_provenance=DataProvenance.REAL)
    session.add(lead)
    session.commit()
    return lead


def _client(handler, counter=None):
    def wrapped(req):
        if counter is not None:
            counter["n"] += 1
        return handler(req)
    return ContactOutClient(ContactOutConfig(api_token="test-token"),
                            http=httpx.Client(transport=httpx.MockTransport(wrapped)),
                            sleep=lambda s: None)


_JANE = {"full_name": "Jane Doe", "title": "VP Engineering",
         "company": {"name": "Acme Corp", "domain": "acme.com"},
         "linkedin_url": "https://linkedin.com/in/janedoe", "work_email": ["jane@acme.com"],
         "work_email_status": "verified", "phone": ["+91-80-1234"], "is_current": True}
_BOB_WRONG = {"full_name": "Bob Wrong", "title": "VP Engineering",
              "company": {"name": "Globex", "domain": "globex.com"},
              "work_email": ["bob@globex.com"], "is_current": True}


def test_discovers_and_persists_matched_poc_only(seed_session):
    lead = _seed(seed_session)
    client = _client(lambda r: httpx.Response(200, json={"profiles": [_JANE, _BOB_WRONG]}))
    summ = discover_pocs_for_lead(seed_session, lead, client=client)
    assert summ.status == "ENRICHED" and summ.candidates_found == 2 and summ.persisted == 1
    poc = summ.pocs[0]
    assert poc.full_name == "Jane Doe" and poc.business_email == "jane@acme.com"
    assert poc.business_phone == "+91-80-1234"
    assert poc.email_status == EmailStatus.VERIFIED_SOURCE
    assert poc.contact_trust_status == "VERIFIED"
    # Wrong-company person is never attached (§18).
    assert all(p.full_name != "Bob Wrong" for p in summ.pocs)


def test_provenance_retained(seed_session):
    lead = _seed(seed_session)
    client = _client(lambda r: httpx.Response(200, json={"profiles": [_JANE]}))
    poc = discover_pocs_for_lead(seed_session, lead, client=client).pocs[0]
    assert poc.contact_source == "ContactOut" and poc.source_type == "contact_enrichment"
    assert poc.data_provenance == DataProvenance.REAL
    assert poc.source_url == "https://linkedin.com/in/janedoe"
    assert poc.source_record_id and poc.last_verified_at is not None


def test_no_fabrication_when_no_email(seed_session):
    lead = _seed(seed_session)
    person = {"full_name": "No Email", "title": "CTO", "company": {"name": "Acme Corp", "domain": "acme.com"},
              "linkedin_url": "https://linkedin.com/in/noemail", "is_current": True}
    client = _client(lambda r: httpx.Response(200, json={"profiles": [person]}))
    poc = discover_pocs_for_lead(seed_session, lead, client=client).pocs[0]
    assert poc.business_email is None and poc.business_phone is None   # never invented


def test_empty_result_is_honest(seed_session):
    lead = _seed(seed_session)
    client = _client(lambda r: httpx.Response(200, json={"profiles": []}))
    summ = discover_pocs_for_lead(seed_session, lead, client=client)
    assert summ.status == "NO_POC_FOUND" and summ.persisted == 0 and not summ.pocs


def test_caching_reuses_without_second_call(seed_session):
    lead = _seed(seed_session)
    counter = {"n": 0}
    client = _client(lambda r: httpx.Response(200, json={"profiles": [_JANE]}), counter)
    discover_pocs_for_lead(seed_session, lead, client=client)
    calls_after_first = counter["n"]
    summ2 = discover_pocs_for_lead(seed_session, lead, client=client)
    assert summ2.status == "CACHED" and counter["n"] == calls_after_first   # no new API call


def test_stale_contact_triggers_refresh(seed_session):
    lead = _seed(seed_session)
    client = _client(lambda r: httpx.Response(200, json={"profiles": [_JANE]}))
    discover_pocs_for_lead(seed_session, lead, client=client)
    # Age the POC beyond the freshness window.
    get_settings().contactout_cache_ttl_hours = 1
    dm = get_pocs_for_lead(seed_session, lead)[0]
    dm.last_verified_at = dm.last_verified_at - timedelta(hours=48)
    seed_session.commit()
    counter = {"n": 0}
    client2 = _client(lambda r: httpx.Response(200, json={"profiles": [_JANE]}), counter)
    summ = discover_pocs_for_lead(seed_session, lead, client=client2)
    assert summ.status == "ENRICHED" and counter["n"] >= 1   # cache expired → real call


def test_dedup_no_duplicate_person(seed_session):
    lead = _seed(seed_session)
    client = _client(lambda r: httpx.Response(200, json={"profiles": [_JANE]}))
    discover_pocs_for_lead(seed_session, lead, client=client)
    discover_pocs_for_lead(seed_session, lead, client=client, force=True)
    rows = seed_session.query(DecisionMaker).filter(DecisionMaker.contact_source == "ContactOut").all()
    assert len(rows) == 1   # updated in place, not duplicated


def test_credit_cap_limits_people_search(seed_session):
    lead = _seed(seed_session, domain=None)   # no domain → name identifier; force people-search fallback
    get_settings().contactout_max_poc_searches_per_opportunity = 2
    counter = {"n": 0}
    # Always return a non-matching person → keeps wanting to search, but cap stops it.
    client = _client(lambda r: httpx.Response(200, json={"profiles": [_BOB_WRONG]}), counter)
    summ = discover_pocs_for_lead(seed_session, lead, client=client)
    assert summ.searches_used <= 2 and summ.status == "NO_POC_FOUND"


def test_not_configured_makes_no_call(seed_session):
    lead = _seed(seed_session)
    get_settings().contactout_api_token = None
    counter = {"n": 0}
    client = _client(lambda r: httpx.Response(200, json={"profiles": [_JANE]}), counter)
    summ = discover_pocs_for_lead(seed_session, lead, client=client)
    assert summ.status == "NOT_CONFIGURED" and counter["n"] == 0 and not summ.pocs


def test_rate_limited_no_fabrication(seed_session):
    lead = _seed(seed_session)
    client = _client(lambda r: httpx.Response(429, headers={"Retry-After": "1"}))
    summ = discover_pocs_for_lead(seed_session, lead, client=client)
    assert summ.status == "RATE_LIMITED" and not summ.pocs and summ.persisted == 0


def test_lead_score_unchanged_by_poc(seed_session):
    lead = _seed(seed_session)
    before = lead.lead_score
    client = _client(lambda r: httpx.Response(200, json={"profiles": [_JANE]}))
    discover_pocs_for_lead(seed_session, lead, client=client)
    seed_session.refresh(lead)
    assert lead.lead_score == before   # POC availability never changes the lead score (§31)


def test_enrich_poc_fills_missing_contact(seed_session):
    lead = _seed(seed_session)
    person = {"full_name": "No Email", "title": "CTO", "company": {"name": "Acme Corp", "domain": "acme.com"},
              "linkedin_url": "https://linkedin.com/in/noemail", "is_current": True}
    disc = _client(lambda r: httpx.Response(200, json={"profiles": [person]}))
    dm = discover_pocs_for_lead(seed_session, lead, client=disc).pocs[0]
    assert dm.business_email is None
    enr = _client(lambda r: httpx.Response(200, json={"profile": {
        "full_name": "No Email", "work_email": ["cto@acme.com"], "work_email_status": "verified"}}))
    summ = enrich_poc(seed_session, dm, client=enr)
    assert summ.status == "ENRICHED"
    seed_session.refresh(dm)
    assert dm.business_email == "cto@acme.com"
