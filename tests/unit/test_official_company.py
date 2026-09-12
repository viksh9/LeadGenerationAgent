"""Official-company intelligence unit tests (Prompt 46) — offline, nothing fabricated.

Covers URL/city normalization, JSON-LD Organization/PostalAddress/ContactPoint
extraction, phone/email/LinkedIn/page-link extraction, Data Trust scoring, and the
provider over a mocked SafeHttpClient (facts + people + multi-location + no-fake).
"""

from __future__ import annotations

from collectors.company.http_client import CareerCollectorError, FetchedPage
from integrations.public_intelligence.models import CompanyContext
from integrations.public_intelligence.official_company import extractors as ex
from integrations.public_intelligence.official_company.normalizer import (
    build_full_address,
    canonical_city,
    location_key,
    normalize_url,
)
from integrations.public_intelligence.official_company.provider import OfficialCompanyProvider
from integrations.public_intelligence.official_company.trust import company_data_trust, field_trust

_ORG = '''<html><head><script type="application/ld+json">
{"@type":"Organization","name":"Acme Technologies","url":"http://acme.com","telephone":"+91 80 1111 2222",
 "email":"info@acme.com","sameAs":["https://www.linkedin.com/company/acme","https://x.com/acme"],
 "address":{"@type":"PostalAddress","streetAddress":"12 MG Road","addressLocality":"Bangalore",
   "addressRegion":"KA","postalCode":"560001","addressCountry":"India"}}
</script></head><body>
<a href="mailto:sales@acme.com">Email</a><a href="tel:+91-80-9999-0000">Call</a>
<a href="/contact-us">Contact</a><a href="/careers">Careers</a><a href="/leadership">Team</a>
<a href="https://linkedin.com/in/someone">personal</a></body></html>'''


# --- normalizer ------------------------------------------------------------- #
def test_normalize_url():
    assert normalize_url("http://Acme.com/") == "https://acme.com"
    assert normalize_url("acme.com") == "https://acme.com"
    assert normalize_url("") is None


def test_canonical_city_uses_geo_map():
    assert canonical_city("Bangalore") == ("Bengaluru", "Karnataka")
    assert canonical_city("Nowhereville") == ("Nowhereville", None)   # unknown passes through
    assert canonical_city(None) == (None, None)


def test_build_full_address_only_present_parts():
    assert build_full_address(city="Bengaluru", country="India") == "Bengaluru, India"
    assert build_full_address() is None


# --- extractors ------------------------------------------------------------- #
def test_extract_org_facts():
    f = ex.extract_org_facts(_ORG)
    assert f.name == "Acme Technologies" and f.telephone == "+91 80 1111 2222"
    assert f.email == "info@acme.com"
    assert f.linkedin_url == "https://www.linkedin.com/company/acme"
    assert f.address.city == "Bangalore" and f.address.postal == "560001"


def test_extract_contacts_from_anchors():
    phones, emails = ex.extract_contacts_from_anchors(_ORG)
    assert "+91-80-9999-0000" in phones and "sales@acme.com" in emails


def test_extract_linkedin_company_never_personal():
    # personal /in/ links must not be returned as the company URL
    html = '<a href="https://linkedin.com/in/jane">j</a>'
    assert ex.extract_linkedin_company(html) is None


def test_discover_page_links():
    links = ex.discover_page_links(_ORG)
    assert links["contact"] == "/contact-us" and links["careers"] == "/careers"


def test_postal_address_missing_parts_stay_none():
    parts = ex.extract_postal_address({"@type": "PostalAddress", "addressLocality": "Pune"})
    assert parts.city == "Pune" and parts.line1 is None and parts.postal is None


# --- trust ------------------------------------------------------------------ #
def test_company_data_trust_max_and_partial():
    assert company_data_trust(identity_confirmed=True, address_confirmed=True, contact_confirmed=True,
                              linkedin_confirmed=True, careers_confirmed=True, fresh=True) == 100
    # only identity + fresh
    assert company_data_trust(identity_confirmed=True, address_confirmed=False, contact_confirmed=False,
                             linkedin_confirmed=False, careers_confirmed=False, fresh=True) == 40
    assert company_data_trust(identity_confirmed=False, address_confirmed=False, contact_confirmed=False,
                             linkedin_confirmed=False, careers_confirmed=False, fresh=False) == 0


def test_field_trust():
    assert field_trust("website_url") == 100 and field_trust("address") == 95


# --- provider (mocked SafeHttpClient) --------------------------------------- #
_HOME = ('<html><head><script type="application/ld+json">{"@type":"Organization",'
         '"name":"Acme","url":"https://acme.com","sameAs":["https://www.linkedin.com/company/acme"]}'
         '</script></head><body><a href="/contact">c</a><a href="/careers">j</a></body></html>')
_CONTACT = ('<html><head><script type="application/ld+json">{"@type":"Organization","email":"info@acme.com",'
            '"telephone":"+91 80 1","address":{"@type":"PostalAddress","streetAddress":"12 MG Rd",'
            '"addressLocality":"Bengaluru","addressCountry":"India"}}</script></head></html>')
_TEAM = ('<html><head><script type="application/ld+json">{"@type":"Organization","employee":'
         '[{"@type":"Person","name":"Jane Doe","jobTitle":"VP Engineering"}]}</script></head></html>')


class _FakeClient:
    def __init__(self, pages, fail_all=False):
        self._pages, self._fail_all = pages, fail_all

    def fetch(self, url, *, enforce_content_type=True):
        if self._fail_all:
            raise CareerCollectorError("403")
        path = url.split("acme.com", 1)[1] if "acme.com" in url else ""
        text = self._pages.get(path)
        if text is None:
            raise CareerCollectorError("404")
        return FetchedPage(url=url, status=200, content_type="text/html", text=text, elapsed_seconds=0.0)


_CTX = CompanyContext(company_id=1, company_name="Acme", normalized_name="acme", domain="acme.com")


def test_provider_extracts_facts_and_people():
    prov = OfficialCompanyProvider(client=_FakeClient({"": _HOME, "/contact": _CONTACT, "/team": _TEAM}))
    res = prov.discover(_CTX, ["VP Engineering"])
    f = res.company_facts
    assert f.website == "https://acme.com" and f.linkedin_url == "https://www.linkedin.com/company/acme"
    assert f.company_email == "info@acme.com" and f.city == "Bengaluru"
    assert f.contact_url and f.careers_url
    assert any(e.field == "address" for e in f.field_evidence)
    assert any(p.full_name == "Jane Doe" for p in res.people)


def test_provider_partial_data_ok():
    # Only a homepage with just identity → partial facts, still valid (no crash, no fake).
    prov = OfficialCompanyProvider(client=_FakeClient({"": _HOME}))
    f = prov.discover(_CTX, []).company_facts
    assert f.website == "https://acme.com"
    assert f.full_address is None and f.company_phone is None   # absent → None, never invented


def test_provider_no_fake_when_all_fetches_fail():
    prov = OfficialCompanyProvider(client=_FakeClient({}, fail_all=True))
    res = prov.discover(_CTX, [])
    assert res.company_facts is None and res.people == []   # SOURCE_UNAVAILABLE → nothing fabricated
