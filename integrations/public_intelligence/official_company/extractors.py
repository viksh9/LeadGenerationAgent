"""Structured-first extractors for official company pages (Prompt 46, §6).

Extraction priority: JSON-LD / schema.org (Organization / Corporation / LocalBusiness
/ PostalAddress / ContactPoint) → published `tel:` / `mailto:` anchors → explicit
social (`sameAs`) links. Pure functions over page HTML — nothing is fabricated: a
value that is not present in the source stays None. Company phone numbers are never
attributed to a person; emails are never guessed from names.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any, Optional

from collectors.company.parsers import _extract_dom, _walk_jsonld

_ORG_TYPES = ("organization", "corporation", "localbusiness")
_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_LINKEDIN_COMPANY_RE = re.compile(r"https?://([a-z]+\.)?linkedin\.com/company/[^/?#\s]+", re.I)
# Path/anchor-text hints for discovering relevant pages.
_PAGE_HINTS = {
    "contact": ("contact", "contact-us", "contactus"),
    "careers": ("careers", "career", "jobs", "join-us", "we-are-hiring"),
    "leadership": ("leadership", "management", "executive", "team", "our-team",
                   "about", "about-us", "people"),
}


@dataclass
class AddressParts:
    line1: Optional[str] = None
    line2: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    postal: Optional[str] = None
    country: Optional[str] = None

    def any(self) -> bool:
        return any((self.line1, self.line2, self.city, self.state, self.postal, self.country))


@dataclass
class OrgFacts:
    name: Optional[str] = None
    url: Optional[str] = None
    telephone: Optional[str] = None
    email: Optional[str] = None
    linkedin_url: Optional[str] = None
    address: AddressParts = field(default_factory=AddressParts)
    same_as: list[str] = field(default_factory=list)
    addresses: list[AddressParts] = field(default_factory=list)


def _first(value: Any) -> Any:
    return value[0] if isinstance(value, list) and value else value


def _str(value: Any) -> Optional[str]:
    value = _first(value)
    if isinstance(value, dict):
        value = value.get("name") or value.get("@value")
    return value.strip() if isinstance(value, str) and value.strip() else None


def extract_postal_address(node: Any) -> AddressParts:
    """Parse a schema.org PostalAddress (dict) into components (nothing invented)."""
    if isinstance(node, str):
        return AddressParts(line1=node.strip() or None)
    if not isinstance(node, dict):
        return AddressParts()
    return AddressParts(
        line1=_str(node.get("streetAddress")),
        city=_str(node.get("addressLocality")),
        state=_str(node.get("addressRegion")),
        postal=_str(node.get("postalCode")),
        country=_str(node.get("addressCountry")),
    )


def _jsonld_nodes(html: str) -> list[dict]:
    nodes: list[dict] = []
    for stype, content in _extract_dom(html).scripts:
        if "ld+json" not in stype:
            continue
        try:
            data = json.loads(content.strip())
        except (json.JSONDecodeError, ValueError):
            continue
        nodes.extend(n for n in _walk_jsonld(data) if isinstance(n, dict))
    return nodes


def extract_org_facts(html: str) -> OrgFacts:
    """Extract Organization/Corporation/LocalBusiness facts from JSON-LD."""
    facts = OrgFacts()
    for node in _jsonld_nodes(html):
        types = str(node.get("@type", "")).lower()
        if not any(t in types for t in _ORG_TYPES):
            continue
        facts.name = facts.name or _str(node.get("name"))
        facts.url = facts.url or _str(node.get("url"))
        facts.telephone = facts.telephone or _str(node.get("telephone"))
        facts.email = facts.email or _clean_email(_str(node.get("email")))
        # contactPoint may carry telephone/email.
        cp = node.get("contactPoint")
        for c in (cp if isinstance(cp, list) else [cp]):
            if isinstance(c, dict):
                facts.telephone = facts.telephone or _str(c.get("telephone"))
                facts.email = facts.email or _clean_email(_str(c.get("email")))
        # address may be one or many PostalAddress nodes.
        addr = node.get("address")
        for a in (addr if isinstance(addr, list) else [addr]):
            parts = extract_postal_address(a)
            if parts.any():
                facts.addresses.append(parts)
        # sameAs → social links (LinkedIn company).
        for link in _as_list(node.get("sameAs")):
            if isinstance(link, str):
                facts.same_as.append(link)
                if not facts.linkedin_url and _LINKEDIN_COMPANY_RE.match(link.strip()):
                    facts.linkedin_url = link.strip()
    if facts.addresses:
        facts.address = facts.addresses[0]
    return facts


def _as_list(v: Any) -> list:
    return v if isinstance(v, list) else ([] if v is None else [v])


def _clean_email(value: Optional[str]) -> Optional[str]:
    if not value:
        return None
    v = value.strip().lower().removeprefix("mailto:")
    return v if _EMAIL_RE.match(v) else None


def extract_contacts_from_anchors(html: str) -> tuple[list[str], list[str]]:
    """Return (phones, emails) from published tel:/mailto: anchors (never guessed)."""
    phones, emails = [], []
    for href, _rel, _text in getattr(_extract_dom(html), "anchors", []):
        h = (href or "").strip()
        low = h.lower()
        if low.startswith("mailto:"):
            e = _clean_email(low.split("?")[0])
            if e and e not in emails:
                emails.append(e)
        elif low.startswith("tel:"):
            num = h[4:].split("?")[0].strip()
            if num and num not in phones:
                phones.append(num)
    return phones, emails


def extract_linkedin_company(html: str) -> Optional[str]:
    """A LinkedIn COMPANY url from sameAs or an anchor — never a personal /in/ URL,
    never constructed from the company name (§15)."""
    facts = extract_org_facts(html)
    if facts.linkedin_url:
        return facts.linkedin_url
    for href, _rel, _text in getattr(_extract_dom(html), "anchors", []):
        m = _LINKEDIN_COMPANY_RE.match((href or "").strip())
        if m:
            return m.group(0)
    return None


def discover_page_links(html: str) -> dict[str, Optional[str]]:
    """Best contact/careers/leadership link (href) found in anchors, by path/text hint.
    Returns raw hrefs (possibly relative) — the caller resolves them against the base."""
    found: dict[str, Optional[str]] = {"contact": None, "careers": None, "leadership": None}
    for href, _rel, text in getattr(_extract_dom(html), "anchors", []):
        h = (href or "").strip()
        if not h or h.startswith(("mailto:", "tel:", "#", "javascript:")):
            continue
        hay = f"{h.lower()} {(text or '').lower()}"
        for key, hints in _PAGE_HINTS.items():
            if found[key] is None and any(hint in hay for hint in hints):
                found[key] = h
    return found
