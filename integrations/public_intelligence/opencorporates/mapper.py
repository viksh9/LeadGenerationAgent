"""Map raw OpenCorporates JSON into typed models (defensive, nothing fabricated)."""

from __future__ import annotations

from typing import Any, Optional

from integrations.public_intelligence.opencorporates.models import (
    OCAddress,
    OCCompany,
    OCOfficer,
    OCSearchResult,
)

_OC_PUBLIC = "https://opencorporates.com/companies/"


def _s(v: Any) -> Optional[str]:
    return v.strip() if isinstance(v, str) and v.strip() else (str(v) if isinstance(v, (int, float)) else None)


def _address(raw: Any) -> OCAddress:
    if isinstance(raw, str):
        return OCAddress(in_full=raw.strip() or None)
    if not isinstance(raw, dict):
        return OCAddress()
    return OCAddress(
        line_1=_s(raw.get("street_address")), city=_s(raw.get("locality")),
        region=_s(raw.get("region")), postal_code=_s(raw.get("postal_code")),
        country=_s(raw.get("country")), in_full=_s(raw.get("in_full")))


def parse_company(node: dict) -> OCCompany:
    """Parse a single OpenCorporates `company` object."""
    c = node.get("company", node) if isinstance(node, dict) else {}
    if not isinstance(c, dict):
        return OCCompany()
    jc = _s(c.get("jurisdiction_code"))
    number = _s(c.get("company_number"))
    addr = _address(c.get("registered_address"))
    if not addr.in_full and _s(c.get("registered_address_in_full")):
        addr.in_full = _s(c.get("registered_address_in_full"))
    prev = [_s(p.get("company_name")) if isinstance(p, dict) else _s(p)
            for p in (c.get("previous_names") or [])]
    industries = []
    for ic in (c.get("industry_codes") or []):
        node_ic = ic.get("industry_code") if isinstance(ic, dict) else ic
        if isinstance(node_ic, dict):
            desc = _s(node_ic.get("description")) or _s(node_ic.get("code"))
            if desc:
                industries.append(desc)
    officers = []
    for o in (c.get("officers") or []):
        node_o = o.get("officer") if isinstance(o, dict) else o
        if isinstance(node_o, dict) and _s(node_o.get("name")):
            officers.append(OCOfficer(name=_s(node_o.get("name")), position=_s(node_o.get("position")),
                                      start_date=_s(node_o.get("start_date")),
                                      end_date=_s(node_o.get("end_date"))))
    src = c.get("source") if isinstance(c.get("source"), dict) else {}
    oc_url = _s(c.get("opencorporates_url")) or (f"{_OC_PUBLIC}{jc}/{number}" if jc and number else None)
    inactive = c.get("inactive")
    return OCCompany(
        name=_s(c.get("name")), legal_name=_s(c.get("name")), company_number=number,
        jurisdiction_code=jc, company_type=_s(c.get("company_type")),
        current_status=_s(c.get("current_status")),
        inactive=bool(inactive) if inactive is not None else None,
        incorporation_date=_s(c.get("incorporation_date")),
        dissolution_date=_s(c.get("dissolution_date")), branch=_s(c.get("branch")),
        registered_address=addr, registry_url=_s(c.get("registry_url")),
        opencorporates_url=oc_url,
        opencorporates_id=(f"{jc}/{number}" if jc and number else None),
        previous_names=[p for p in prev if p], industry_codes=industries, officers=officers,
        publisher=_s(src.get("publisher")), publisher_url=_s(src.get("url")),
        publisher_retrieved_at=_s(src.get("retrieved_at")))


def parse_search(raw: dict) -> OCSearchResult:
    if not isinstance(raw, dict):
        return OCSearchResult()
    results = raw.get("results") or {}
    companies = results.get("companies") or []
    return OCSearchResult(
        companies=[parse_company(c) for c in companies if isinstance(c, dict)],
        total_count=results.get("total_count"))


def parse_company_detail(raw: dict) -> Optional[OCCompany]:
    if not isinstance(raw, dict):
        return None
    company = (raw.get("results") or {}).get("company")
    return parse_company({"company": company}) if isinstance(company, dict) else None
