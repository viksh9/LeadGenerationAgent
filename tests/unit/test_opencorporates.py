"""OpenCorporates unit tests (Prompt 47) — offline, nothing fabricated.

Config, mapper (search/detail/registered address/officers/industry), entity matching
(exact/ambiguous/no-match, India-first, never verified on name alone), India
classification, Data Trust (§18), and client error mapping (401/403/404/429/5xx/timeout).
"""

from __future__ import annotations

import httpx
import pytest

from config.settings import Settings
from integrations.public_intelligence.official_company.trust import company_data_trust
from integrations.public_intelligence.opencorporates.client import OpenCorporatesClient
from integrations.public_intelligence.opencorporates.exceptions import (
    OpenCorporatesAuthError,
    OpenCorporatesNotConfigured,
    OpenCorporatesRateLimited,
    OpenCorporatesUnavailable,
)
from integrations.public_intelligence.opencorporates.mapper import (
    parse_company_detail,
    parse_search,
)
from integrations.public_intelligence.opencorporates.matching import (
    GLOBAL_WITH_INDIA_PRESENCE,
    INDIA_ENTITY,
    NON_INDIA,
    LIKELY_MATCH,
    MULTIPLE_MATCHES,
    NO_MATCH,
    VERIFIED_MATCH,
    classify_india_entity,
    match_entity,
)
from integrations.public_intelligence.opencorporates.models import OCCompany


# --- config ----------------------------------------------------------------- #
def test_config_status():
    assert Settings(_env_file=None).opencorporates_config_status == "NOT_CONFIGURED"
    assert Settings(_env_file=None, OPENCORPORATES_API_TOKEN="t").opencorporates_config_status == "CONFIGURED"
    assert Settings(_env_file=None, OPENCORPORATES_API_TOKEN="t",
                    OPENCORPORATES_ENABLED=False).opencorporates_config_status == "DISABLED"
    assert Settings(_env_file=None).opencorporates_api_version == "v0.4"


# --- mapper ----------------------------------------------------------------- #
_SEARCH = {"results": {"total_count": 1, "companies": [{"company": {
    "name": "Infosys Limited", "company_number": "L85110KA1981PLC013115", "jurisdiction_code": "in_ka",
    "current_status": "Active", "registry_url": "https://mca.gov.in/x",
    "opencorporates_url": "https://opencorporates.com/companies/in_ka/L85110KA1981PLC013115"}}]}}
_DETAIL = {"results": {"company": {
    "name": "Infosys Limited", "company_number": "L85110KA1981PLC013115", "jurisdiction_code": "in_ka",
    "current_status": "Active", "incorporation_date": "1981-07-02",
    "registered_address": {"street_address": "Electronics City", "locality": "Bengaluru",
                           "region": "Karnataka", "postal_code": "560100", "country": "India"},
    "industry_codes": [{"industry_code": {"description": "Computer programming"}}],
    "officers": [{"officer": {"name": "Salil Parekh", "position": "director", "start_date": "2018"}}],
    "previous_names": [{"company_name": "Infosys Technologies Limited"}],
    "source": {"publisher": "Ministry of Corporate Affairs", "url": "https://mca.gov.in"}}}}


def test_parse_search():
    res = parse_search(_SEARCH)
    assert res.total_count == 1 and len(res.companies) == 1
    c = res.companies[0]
    assert c.company_number == "L85110KA1981PLC013115" and c.jurisdiction_code == "in_ka"


def test_parse_detail_address_officers_industry():
    c = parse_company_detail(_DETAIL)
    assert c.registered_address.city == "Bengaluru" and c.registered_address.postal_code == "560100"
    assert c.officers and c.officers[0].name == "Salil Parekh"
    assert "Computer programming" in c.industry_codes
    assert "Infosys Technologies Limited" in c.previous_names


def test_parse_missing_stays_none():
    c = parse_company_detail({"results": {"company": {"name": "X"}}})
    assert c.company_number is None and not c.registered_address.any() and c.officers == []


# --- matching --------------------------------------------------------------- #
def _oc(name, jc=None, number=None, prev=None):
    return OCCompany(name=name, legal_name=name, jurisdiction_code=jc, company_number=number,
                     previous_names=prev or [])


def test_verified_match_requires_corroboration():
    # single exact India match WITH a company number → VERIFIED (not name-alone)
    best, st = match_entity(company_name="Infosys",
                            candidates=[_oc("Infosys Limited", "in_ka", "L123")])
    assert st == VERIFIED_MATCH and best.company_number == "L123"


def test_single_exact_without_number_is_likely():
    best, st = match_entity(company_name="Infosys", candidates=[_oc("Infosys Limited", "in_ka", None)])
    assert st == LIKELY_MATCH


def test_ambiguous_multiple_matches():
    best, st = match_entity(company_name="Acme",
                            candidates=[_oc("Acme", "in_ka", "1"), _oc("Acme", "in_mh", "2")])
    assert st == MULTIPLE_MATCHES


def test_no_match_on_name_mismatch():
    _, st = match_entity(company_name="Infosys", candidates=[_oc("Globex Corp", "us_de", "9")])
    assert st == NO_MATCH


def test_india_first_prefers_indian_entity():
    best, st = match_entity(company_name="Acme",
                            candidates=[_oc("Acme", "us_de", "1"), _oc("Acme", "in_ka", "2")])
    assert best.jurisdiction_code == "in_ka"   # India preferred


# --- India classification --------------------------------------------------- #
def test_india_classification():
    assert classify_india_entity(_oc("X", "in_ka", "1"), india_presence=True) == INDIA_ENTITY
    # non-India legal entity + India office -> GLOBAL_WITH_INDIA_PRESENCE (§15)
    assert classify_india_entity(_oc("X", "us_de", "1"), india_presence=True) == GLOBAL_WITH_INDIA_PRESENCE
    assert classify_india_entity(_oc("X", "us_de", "1"), india_presence=False) == NON_INDIA


# --- Data Trust (§18) ------------------------------------------------------- #
def test_data_trust_framework():
    assert company_data_trust(identity_confirmed=True, website_confirmed=True, address_confirmed=True,
                              registry_confirmed=True, opencorporates_match=True,
                              careers_confirmed=True, fresh=True) == 100
    # official-only (no registry, no OC): 30+20+15+5+5 = 75
    assert company_data_trust(identity_confirmed=True, website_confirmed=True, address_confirmed=True,
                              careers_confirmed=True, fresh=True) == 75
    assert company_data_trust(identity_confirmed=False) == 0


# --- client error mapping --------------------------------------------------- #
@pytest.fixture
def _token():
    from config import get_settings
    s = get_settings(); prev = s.opencorporates_api_token
    s.opencorporates_api_token = "tok"
    yield
    s.opencorporates_api_token = prev


def _client(handler):
    return OpenCorporatesClient(http=httpx.Client(transport=httpx.MockTransport(handler)),
                                sleep=lambda s: None)


def test_no_token_not_configured():
    from config import get_settings
    prev = get_settings().opencorporates_api_token
    get_settings().opencorporates_api_token = None
    try:
        with pytest.raises(OpenCorporatesNotConfigured):
            OpenCorporatesClient().search_companies("Infosys")
    finally:
        get_settings().opencorporates_api_token = prev


def test_token_passed_as_param_and_search_ok(_token):
    seen = {}

    def h(req):
        seen["query"] = str(req.url.query)
        return httpx.Response(200, json=_SEARCH)

    res = parse_search(_client(h).search_companies("Infosys") or {})
    assert "api_token=tok" in seen["query"] and len(res.companies) == 1


@pytest.mark.parametrize("code,exc", [(401, OpenCorporatesAuthError), (403, OpenCorporatesAuthError),
                                      (429, OpenCorporatesRateLimited), (503, OpenCorporatesUnavailable)])
def test_error_mapping(_token, code, exc):
    hdrs = {"Retry-After": "1"} if code == 429 else {}
    with pytest.raises(exc):
        OpenCorporatesClient(http=httpx.Client(transport=httpx.MockTransport(
            lambda r: httpx.Response(code, headers=hdrs))), sleep=lambda s: None).search_companies("X")


def test_404_returns_none(_token):
    assert _client(lambda r: httpx.Response(404)).search_companies("X") is None


def test_timeout_unavailable(_token):
    def h(req):
        raise httpx.ConnectTimeout("boom", request=req)
    with pytest.raises(OpenCorporatesUnavailable):
        _client(h).search_companies("X")
