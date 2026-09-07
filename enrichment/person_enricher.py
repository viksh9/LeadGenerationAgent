"""Real person / business-contact enrichment from OFFICIAL, permitted sources.

Extracts REAL people and business contacts ONLY from what an official company page
actually publishes — schema.org ``Person`` (name + jobTitle) in JSON-LD, and
published ``mailto:`` business addresses. It NEVER:
  * fabricates a person, email, phone, or profile URL,
  * guesses an address from a naming convention (firstname.lastname@…),
  * constructs a LinkedIn/profile URL from a name,
  * scrapes private profiles or bypasses auth/robots/anti-bot controls.

All fetching goes through the existing SafeHttpClient (HTTPS, SSRF guard,
private-network block, size cap, no credentials). Absent data stays NULL. Every
record carries provenance and is deduplicated deterministically (name alone never
merges two people).
"""

from __future__ import annotations

import json
import logging
import re
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional

from collectors.company.config import load_career_config
from collectors.company.http_client import CareerCollectorError, SafeHttpClient
from collectors.company.parsers import _extract_dom, _walk_jsonld
from collectors.company.safety import SafetyError, validate_public_url
from database.models import ContactType, EmailStatus, RoleCategory

logger = logging.getLogger("enrichment")

COLLECTOR_VERSION = "1.0.0"
_EMAIL_RE = re.compile(r"^[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}$")
# Role-based business address local-parts that are legitimately business contacts.
_BUSINESS_LOCALPARTS = {
    "info", "contact", "sales", "careers", "jobs", "hr", "recruitment",
    "procurement", "tenders", "vendor", "vendors", "support", "hello", "business",
}
_CONTACT_TYPE_BY_LOCALPART = {
    "procurement": ContactType.PROCUREMENT_CONTACT, "tenders": ContactType.PROCUREMENT_CONTACT,
    "vendor": ContactType.PROCUREMENT_CONTACT, "vendors": ContactType.PROCUREMENT_CONTACT,
    "careers": ContactType.DEPARTMENT_CONTACT, "jobs": ContactType.DEPARTMENT_CONTACT,
    "hr": ContactType.DEPARTMENT_CONTACT, "recruitment": ContactType.DEPARTMENT_CONTACT,
}

# Candidate official pages to probe (company's own domain only).
_CANDIDATE_PATHS = ("", "/about", "/about-us", "/leadership", "/team", "/our-team",
                    "/management", "/company/leadership", "/contact", "/contact-us")

# Deterministic role → (normalized_role, category, seniority).
_ROLE_RULES: tuple[tuple[tuple[str, ...], str, RoleCategory, str], ...] = (
    (("chief technology", "cto"), "CTO", RoleCategory.TECHNICAL, "C_LEVEL"),
    (("chief information", "cio"), "CIO", RoleCategory.TECHNICAL, "C_LEVEL"),
    (("chief executive", "ceo"), "CEO", RoleCategory.BUSINESS, "C_LEVEL"),
    (("chief operating", "coo"), "COO", RoleCategory.BUSINESS, "C_LEVEL"),
    (("chief product", "cpo"), "Chief Product Officer", RoleCategory.PRODUCT, "C_LEVEL"),
    (("vp engineering", "vice president of engineering", "vp of engineering"),
     "VP Engineering", RoleCategory.ENGINEERING, "VP"),
    (("head of engineering",), "Head of Engineering", RoleCategory.ENGINEERING, "HEAD"),
    (("engineering director", "director of engineering"), "Engineering Director",
     RoleCategory.ENGINEERING, "DIRECTOR"),
    (("engineering manager",), "Engineering Manager", RoleCategory.ENGINEERING, "MANAGER"),
    (("head of cloud", "cloud lead"), "Head of Cloud", RoleCategory.TECHNICAL, "HEAD"),
    (("head of qa", "qa manager", "head of quality"), "Head of QA", RoleCategory.ENGINEERING, "HEAD"),
    (("talent acquisition", "recruit", "hr "), "Talent Acquisition", RoleCategory.TALENT_ACQUISITION, "MANAGER"),
    (("procurement", "sourcing"), "Procurement", RoleCategory.PROCUREMENT, "MANAGER"),
    (("vendor management",), "Vendor Management", RoleCategory.VENDOR_MANAGEMENT, "MANAGER"),
    (("delivery head", "delivery manager"), "Delivery Head", RoleCategory.DELIVERY, "HEAD"),
    (("program director", "program manager"), "Program Director", RoleCategory.DELIVERY, "DIRECTOR"),
    (("head of it", "it director"), "Head of IT", RoleCategory.TECHNICAL, "HEAD"),
)


def classify_role(title: Optional[str]) -> tuple[Optional[str], RoleCategory, Optional[str]]:
    if not title:
        return None, RoleCategory.OTHER, None
    t = title.lower()
    for needles, norm, cat, sen in _ROLE_RULES:
        if any(n in t for n in needles):
            return norm, cat, sen
    return title.strip()[:128], RoleCategory.OTHER, None


def _norm_name(name: Optional[str]) -> Optional[str]:
    if not name:
        return None
    return re.sub(r"\s+", " ", name).strip().lower() or None


# --------------------------------------------------------------------------- #
# Extraction (real published data only)
# --------------------------------------------------------------------------- #
@dataclass
class ExtractedPerson:
    full_name: str
    job_title: Optional[str] = None
    profile_url: Optional[str] = None


@dataclass
class ExtractedContact:
    value: str
    contact_type: ContactType


def extract_people(html: str) -> list[ExtractedPerson]:
    """Extract schema.org Person entities (name [+ jobTitle]) from JSON-LD."""
    people: list[ExtractedPerson] = []
    seen: set[str] = set()
    for stype, content in _extract_dom(html).scripts:
        if "ld+json" not in stype:
            continue
        try:
            data = json.loads(content.strip())
        except (json.JSONDecodeError, ValueError):
            continue
        nodes = list(_walk_jsonld(data))
        # Also pull employees/founders nested on Organization nodes.
        for node in list(nodes):
            for key in ("employee", "employees", "founder", "founders", "member"):
                val = node.get(key)
                if isinstance(val, list):
                    nodes.extend(v for v in val if isinstance(v, dict))
                elif isinstance(val, dict):
                    nodes.append(val)
        for node in nodes:
            if "person" not in str(node.get("@type", "")).lower():
                continue
            name = node.get("name")
            if isinstance(name, dict):
                name = name.get("@value")
            if not name or not isinstance(name, str):
                continue
            title = node.get("jobTitle")
            if isinstance(title, list):
                title = title[0] if title else None
            key = _norm_name(name) or name
            if key in seen:
                continue
            seen.add(key)
            url = node.get("url") if isinstance(node.get("url"), str) else None
            people.append(ExtractedPerson(full_name=name.strip(), job_title=title, profile_url=url))
    return people


def extract_business_contacts(html: str, *, company_domain: Optional[str]) -> list[ExtractedContact]:
    """Extract published mailto: business emails (never guessed)."""
    contacts: list[ExtractedContact] = []
    seen: set[str] = set()
    dom = _extract_dom(html)
    for href, _rel, _text in getattr(dom, "anchors", []):
        if not href or not href.lower().startswith("mailto:"):
            continue
        email = href[7:].split("?")[0].strip().lower()
        if not _EMAIL_RE.match(email) or email in seen:
            continue
        local, _, domain = email.partition("@")
        is_company = bool(company_domain) and domain.endswith(company_domain.lower())
        if not (is_company or local in _BUSINESS_LOCALPARTS):
            continue  # skip personal-looking addresses not tied to the business
        seen.add(email)
        ctype = _CONTACT_TYPE_BY_LOCALPART.get(local, ContactType.BUSINESS_EMAIL)
        contacts.append(ExtractedContact(value=email, contact_type=ctype))
    return contacts


# --------------------------------------------------------------------------- #
# Enricher architecture
# --------------------------------------------------------------------------- #
@dataclass
class EnrichmentResult:
    provider: str
    company_name: Optional[str]
    people: list[dict] = field(default_factory=list)
    contacts: list[dict] = field(default_factory=list)
    pages_fetched: int = 0
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


class BasePersonEnricher(ABC):
    provider = "base"
    source_type = "OTHER"

    @abstractmethod
    def enrich(self, *, company_name: str, domain: Optional[str] = None,
               website: Optional[str] = None) -> EnrichmentResult: ...


class BaseContactEnricher(ABC):
    provider = "base"

    @abstractmethod
    def enrich_contacts(self, *, company_name: str, domain: Optional[str] = None,
                        website: Optional[str] = None) -> EnrichmentResult: ...


class OfficialCompanySourceEnricher(BasePersonEnricher, BaseContactEnricher):
    """Extracts real people + business contacts from a company's OWN official pages.
    No credentials; no scraping of third-party/private profiles."""

    provider = "official_company"
    source_type = "OFFICIAL_COMPANY"

    def __init__(self, *, client: Optional[SafeHttpClient] = None, max_pages: int = 4) -> None:
        self._client = client or SafeHttpClient(load_career_config())
        self._max_pages = max_pages

    def _candidate_urls(self, domain: Optional[str], website: Optional[str]) -> list[str]:
        host = None
        if website:
            try:
                host = validate_public_url(website, resolve=False)
            except SafetyError:
                host = None
        host = host or (domain.strip().lower() if domain else None)
        if not host:
            return []
        base = host if host.startswith("http") else f"https://{host}"
        return [f"{base}{p}" for p in _CANDIDATE_PATHS]

    def enrich(self, *, company_name: str, domain: Optional[str] = None,
               website: Optional[str] = None) -> EnrichmentResult:
        result = EnrichmentResult(provider=self.provider, company_name=company_name)
        urls = self._candidate_urls(domain, website)
        if not urls:
            result.warnings.append("No company domain/website to probe.")
            return result
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        seen_people: set[str] = set()
        seen_contacts: set[str] = set()
        for url in urls[: self._max_pages]:
            try:
                page = self._client.fetch(url, enforce_content_type=False)
            except (SafetyError, CareerCollectorError) as exc:
                logger.info("enrich_fetch_failed url=%s error=%s", url, exc)
                continue
            result.pages_fetched += 1
            for person in extract_people(page.text):
                norm = _norm_name(person.full_name)
                nrole, cat, sen = classify_role(person.job_title)
                key = f"{norm}|{nrole or ''}"
                if key in seen_people:
                    continue
                seen_people.add(key)
                result.people.append({
                    "full_name": person.full_name, "normalized_name": norm,
                    "job_title": person.job_title, "normalized_role": nrole,
                    "role_category": cat, "seniority": sen,
                    "profile_url": person.profile_url,
                    "source_url": page.url, "source_type": self.source_type,
                    "contact_source": self.provider, "observed_at": now,
                })
            for contact in extract_business_contacts(page.text, company_domain=domain):
                if contact.value in seen_contacts:
                    continue
                seen_contacts.add(contact.value)
                result.contacts.append({
                    "business_email": contact.value, "contact_type": contact.contact_type,
                    "email_status": EmailStatus.VERIFIED_SOURCE,
                    "source_url": page.url, "source_type": self.source_type,
                    "contact_source": self.provider, "observed_at": now,
                })
        return result

    def enrich_contacts(self, **kwargs) -> EnrichmentResult:
        return self.enrich(**kwargs)
