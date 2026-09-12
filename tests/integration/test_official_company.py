"""Official-company intelligence: persistence + API (Prompt 46).

Isolated DB. The official-company provider is driven by a mocked SafeHttpClient
(no network). Verifies Company field persistence, CompanyLocation, field-level
evidence (conflicts retained), Data Trust, caching, source priority, and the API.
"""

from __future__ import annotations

from datetime import timedelta

import api.main
from api.dependencies import get_session
from collectors.company.http_client import CareerCollectorError, FetchedPage
from config import get_settings
from database.models import (
    Company,
    CompanyFieldEvidence,
    CompanyLocation,
    DataProvenance,
)
from enrichment.public_intelligence_service import discover_company_intelligence
from integrations.public_intelligence.official_company.provider import OfficialCompanyProvider

_HOME = ('<html><head><script type="application/ld+json">{"@type":"Organization","name":"Acme",'
         '"url":"https://acme.com","telephone":"+91 80 1111 2222",'
         '"sameAs":["https://www.linkedin.com/company/acme"]}'
         '</script></head><body><a href="/contact">c</a><a href="/careers">j</a></body></html>')
_CONTACT = ('<html><head><script type="application/ld+json">{"@type":"Organization","email":"info@acme.com",'
            '"address":{"@type":"PostalAddress","streetAddress":"12 MG Road","addressLocality":"Bangalore",'
            '"postalCode":"560001","addressCountry":"India"}}</script></head></html>')


class _FakeClient:
    def fetch(self, url, *, enforce_content_type=True):
        path = url.split("acme.com", 1)[1] if "acme.com" in url else ""
        text = {"": _HOME, "/company": _HOME, "/contact": _CONTACT}.get(path)
        if text is None:
            raise CareerCollectorError("404")
        return FetchedPage(url=url, status=200, content_type="text/html", text=text, elapsed_seconds=0.0)


def _seed_company(session, *, name="Acme", domain="acme.com"):
    c = Company(canonical_name=name, normalized_name=name.lower(), primary_domain=domain,
                data_provenance=DataProvenance.REAL)
    session.add(c)
    session.commit()
    return c


def _provider():
    return OfficialCompanyProvider(client=_FakeClient())


def test_discovery_persists_company_facts(seed_session):
    company = _seed_company(seed_session)
    summ = discover_company_intelligence(seed_session, company, providers=[_provider()])
    assert summ.status in ("SUCCESS", "PARTIAL")
    seed_session.refresh(company)
    assert company.website == "https://acme.com"
    assert company.company_phone == "+91 80 1111 2222"
    assert company.company_email == "info@acme.com"
    assert company.full_address and "Bengaluru" in company.full_address   # canonicalized
    assert company.headquarters_city == "Bengaluru"
    assert company.linkedin_url == "https://www.linkedin.com/company/acme"
    assert company.careers_url and company.data_trust_score >= 90
    assert company.official_verified_at is not None


def test_location_and_evidence_persisted(seed_session):
    company = _seed_company(seed_session)
    discover_company_intelligence(seed_session, company, providers=[_provider()])
    locs = seed_session.query(CompanyLocation).filter_by(company_id=company.id).all()
    assert len(locs) == 1 and locs[0].city == "Bengaluru" and locs[0].is_headquarters
    ev = seed_session.query(CompanyFieldEvidence).filter_by(company_id=company.id).all()
    fields = {e.field for e in ev}
    assert {"website_url", "company_email", "address", "linkedin_url"} <= fields
    addr = next(e for e in ev if e.field == "address")
    assert addr.source == "Official Company Contact Page" and addr.source_url.endswith("/contact")
    assert addr.trust_score == 95


def test_no_fake_when_source_unavailable(seed_session):
    company = _seed_company(seed_session, name="Ghost", domain=None)   # no domain to probe
    summ = discover_company_intelligence(seed_session, company, providers=[_provider()])
    assert summ.status == "SOURCE_UNAVAILABLE"
    seed_session.refresh(company)
    assert company.website is None and company.full_address is None   # nothing fabricated


def test_caching_freshness(seed_session):
    company = _seed_company(seed_session)
    discover_company_intelligence(seed_session, company, providers=[_provider()])
    # A second call within TTL reuses (does not require providers).
    summ2 = discover_company_intelligence(seed_session, company, providers=[])
    assert summ2.status == "SUCCESS" and "freshness window" in summ2.reason


def test_conflicting_evidence_retained(seed_session):
    company = _seed_company(seed_session)
    discover_company_intelligence(seed_session, company, providers=[_provider()])
    # A different source reports a different address — must be retained, not overwritten.
    seed_session.add(CompanyFieldEvidence(
        company_id=company.id, field="address", value="99 Other Rd, Hyderabad",
        source="Wikidata", source_type="wikidata_entity", source_url="https://www.wikidata.org/wiki/Q1",
        source_priority=4, trust_score=60, data_provenance=DataProvenance.REAL))
    seed_session.commit()
    addr_rows = seed_session.query(CompanyFieldEvidence).filter_by(
        company_id=company.id, field="address").all()
    assert len(addr_rows) == 2   # both retained (§22)


# --------------------------------------------------------------------------- #
# API
# --------------------------------------------------------------------------- #
def _seed_via_client(client):
    session = next(api.main.app.dependency_overrides[get_session]())
    c = Company(canonical_name="Acme", normalized_name="acme", primary_domain="acme.com",
                website="https://acme.com", full_address="12 MG Road, Bengaluru, India",
                headquarters_city="Bengaluru", careers_url="https://acme.com/careers",
                data_trust_score=100, data_provenance=DataProvenance.REAL)
    session.add(c)
    session.flush()
    session.add(CompanyFieldEvidence(company_id=c.id, field="website_url", value="https://acme.com",
                source="Official Company Website", source_type="company_website",
                source_url="https://acme.com", source_priority=1, trust_score=100))
    cid = c.id
    session.commit()
    session.close()
    return cid


def test_api_company_profile(client):
    cid = _seed_via_client(client)
    body = client.get(f"/companies/{cid}/public-intelligence").json()
    assert body["website"] == "https://acme.com" and body["data_trust_score"] == 100
    assert body["city"] == "Bengaluru"
    assert len(body["field_sources"]) == 1
    assert body["field_sources"][0]["source_url"] == "https://acme.com"   # clickable source URL


def test_api_sources_endpoint(client):
    cid = _seed_via_client(client)
    rows = client.get(f"/companies/{cid}/sources").json()
    assert len(rows) == 1 and rows[0]["field"] == "website_url"


def test_api_discover_rbac(client, monkeypatch):
    from config import settings as sm
    settings = sm.get_settings()
    monkeypatch.setattr(settings, "admin_api_key", "secret")
    monkeypatch.setattr(settings, "public_intelligence_enabled", False)   # short-circuit (no network)
    cid = _seed_via_client(client)
    assert client.post(f"/companies/{cid}/public-intelligence/discover").status_code == 403
    ok = client.post(f"/companies/{cid}/public-intelligence/discover", headers={"X-Admin-Key": "secret"})
    assert ok.status_code == 200 and ok.json()["status"] == "SOURCE_UNAVAILABLE"


def test_api_discover_404(client):
    assert client.post("/companies/999999/public-intelligence/discover").status_code == 404
