"""Official Company Website provider (Prompt 46).

Fetches only publicly-accessible pages of the company's OWN verified domain (via the
SSRF-safe, robots-respecting SafeHttpClient), structured-data first, and extracts real
company facts — website, address (+ multiple locations), company phone/email, LinkedIn
company URL, and contact/careers/leadership page links — each with field-level
provenance, an evidence snippet, and a trust score. It also extracts publicly-listed
people. Nothing is fabricated: absent facts stay None; access denial → the page is
simply skipped (§5/§29). Because we only ever fetch the company's own domain, facts
are inherently identity-verified (§24).
"""

from __future__ import annotations

import logging
from typing import Optional

from collectors.company.config import load_career_config
from collectors.company.http_client import CareerCollectorError, SafeHttpClient
from collectors.company.safety import SafetyError, validate_public_url
from config import get_settings
from enrichment.person_enricher import extract_business_contacts, extract_people
from integrations.public_intelligence.base import PublicIntelligenceProvider
from integrations.public_intelligence.models import (
    MATCH_VERIFIED,
    CompanyContext,
    CompanyFieldEvidenceRecord,
    CompanyLocationRecord,
    PublicCompanyFacts,
    PublicContact,
    PublicPerson,
)
from integrations.public_intelligence.official_company import extractors as ex
from integrations.public_intelligence.official_company.normalizer import (
    build_full_address,
    canonical_city,
    normalize_url,
)
from integrations.public_intelligence.official_company.trust import field_trust

logger = logging.getLogger("integrations.public_intelligence")

# Candidate paths (§4) — bounded, relevant pages only; never a full crawl. Ordered by
# value so the most useful pages are covered first within the per-company page budget.
_CANDIDATE_PATHS = ("", "/about", "/contact", "/contact-us", "/leadership", "/team",
                    "/careers", "/locations", "/about-us", "/management", "/our-team",
                    "/executive-team", "/office-locations", "/company", "/press")

# page_role -> (source label, source_type, priority) per §1.
_ROLE_META = {
    "website": ("Official Company Website", "company_website", 1),
    "contact": ("Official Company Contact Page", "company_contact_page", 2),
    "leadership": ("Official Company Leadership Page", "company_leadership_page", 3),
    "careers": ("Official Company Careers Page", "company_careers_page", 4),
}


def _page_role(path: str) -> str:
    p = path.lower()
    if any(k in p for k in ("/contact", "/locations", "/office")):
        return "contact"
    if any(k in p for k in ("/leadership", "/management", "/executive", "/team", "/about", "/press")):
        return "leadership"
    if any(k in p for k in ("/careers", "/career", "/jobs")):
        return "careers"
    return "website"


def _resolve(base: str, href: Optional[str]) -> Optional[str]:
    if not href:
        return None
    href = href.strip()
    if href.startswith("http"):
        return href
    if href.startswith("/"):
        return f"{base}{href}"
    return f"{base}/{href}"


class OfficialCompanyProvider(PublicIntelligenceProvider):
    name = "official_company"
    source_label = "Official Company Website"
    source_type = "company_website"

    def __init__(self, *, client: Optional[SafeHttpClient] = None) -> None:
        s = get_settings()
        self._client = client or SafeHttpClient(load_career_config())
        self._max_pages = max(1, s.official_company_max_pages_per_company)
        self._fetch_cache: dict[str, list[tuple[str, str, str]]] = {}

    # --- fetching (once per company; shared by facts + people) --------------- #
    def _base_url(self, ctx: CompanyContext) -> Optional[str]:
        host = None
        if ctx.website:
            try:
                host = validate_public_url(ctx.website, resolve=False)
            except SafetyError:
                host = None
        host = host or (ctx.domain.strip().lower() if ctx.domain else None)
        if not host:
            return None
        return host if host.startswith("http") else f"https://{host}"

    def _fetch_pages(self, ctx: CompanyContext) -> list[tuple[str, str, str]]:
        key = f"{ctx.company_name}|{ctx.domain}|{ctx.website}"
        if key in self._fetch_cache:
            return self._fetch_cache[key]
        base = self._base_url(ctx)
        pages: list[tuple[str, str, str]] = []   # (role, url, text)
        if not base:
            self._fetch_cache[key] = pages
            return pages
        for path in _CANDIDATE_PATHS[: self._max_pages]:
            url = f"{base}{path}"
            try:
                page = self._client.fetch(url, enforce_content_type=False)
            except (SafetyError, CareerCollectorError) as exc:
                logger.info("official_company.error url=%s reason=%s", url, type(exc).__name__)
                continue
            pages.append((_page_role(path), page.url, page.text))
        self._fetch_cache[key] = pages
        return pages

    # --- company facts ------------------------------------------------------- #
    def discover_company(self, ctx: CompanyContext) -> Optional[PublicCompanyFacts]:
        pages = self._fetch_pages(ctx)
        if not pages:
            return None
        base = self._base_url(ctx)
        facts = PublicCompanyFacts(source=self.name, source_label=self.source_label,
                                   source_url=base)
        ev: list[CompanyFieldEvidenceRecord] = []
        recorded: set[tuple] = set()

        def record(field, value, role, page_url, evidence_text=None):
            label, stype, prio = _ROLE_META[role]
            dedup = (field, label, value)
            if not value or dedup in recorded:
                return
            recorded.add(dedup)
            ev.append(CompanyFieldEvidenceRecord(
                field=field, value=value, source=label, source_type=stype, source_url=page_url,
                evidence_text=evidence_text, source_priority=prio, trust_score=field_trust(field)))

        # Website (canonical) — always from the site we reached.
        facts.website = normalize_url((pages[0][2] and base) or base)
        record("website_url", facts.website, "website", base)

        seen_locations: set[str] = set()
        for role, url, text in pages:
            org = ex.extract_org_facts(text)
            anchors_phones, anchors_emails = ex.extract_contacts_from_anchors(text)
            links = ex.discover_page_links(text)

            # LinkedIn company URL (explicit only).
            li = ex.extract_linkedin_company(text)
            if li and not facts.linkedin_url:
                facts.linkedin_url = li
                record("linkedin_url", li, role, url, "sameAs / social link")

            # Phone (org telephone or published tel:), preferring contact pages.
            phone = org.telephone or (anchors_phones[0] if anchors_phones else None)
            if phone and (not facts.company_phone or role == "contact"):
                facts.company_phone = phone.strip()
                record("company_phone", facts.company_phone, role, url, "published telephone")

            # Email (org email or published mailto:), preferring contact pages.
            email = org.email or (anchors_emails[0] if anchors_emails else None)
            if email:
                email = email.strip()
                if email.lower().startswith("mailto:"):
                    email = email[7:].split("?")[0].strip()   # defensive: strip any stray prefix
            if email and (not facts.company_email or role == "contact"):
                facts.company_email = email
                record("company_email", facts.company_email, role, url, "published email")

            # Addresses (structured PostalAddress) → canonical + locations.
            for parts in (org.addresses or []):
                city, state = canonical_city(parts.city)
                if not state:
                    state = parts.state   # fall back to the raw region when unmapped
                full = build_full_address(line1=parts.line1, line2=parts.line2, city=city,
                                          state=state, postal=parts.postal, country=parts.country)
                if not full:
                    continue
                lkey = full.lower()
                if lkey in seen_locations:
                    continue
                seen_locations.add(lkey)
                is_hq = role in ("contact", "website") and len(seen_locations) == 1
                facts.locations.append(CompanyLocationRecord(
                    address_line_1=parts.line1, address_line_2=parts.line2, city=city,
                    state_or_region=state, postal_code=parts.postal, country=parts.country,
                    full_address=full, location_type="HEADQUARTERS" if is_hq else "OFFICE",
                    is_headquarters=is_hq, source=_ROLE_META[role][0], source_url=url))
                if not facts.full_address:   # canonical company address = first found
                    facts.address_line_1, facts.address_line_2 = parts.line1, parts.line2
                    facts.city, facts.state_or_region = city, state
                    facts.postal_code, facts.country = parts.postal, (parts.country or facts.country)
                    facts.full_address = full
                    record("address", full, role, url, full)

            # Page links (contact/careers/leadership) — resolved absolute.
            for kind, attr in (("contact", "contact_url"), ("careers", "careers_url"),
                               ("leadership", "leadership_url")):
                if getattr(facts, attr):
                    continue
                # The fetched page itself counts (e.g. we reached /contact).
                candidate = url if _page_role(url) == kind else _resolve(base, links.get(kind))
                if candidate:
                    setattr(facts, attr, normalize_url(candidate))
                    field = attr
                    role_for = {"contact_url": "contact", "careers_url": "careers",
                                "leadership_url": "leadership"}[attr]
                    record(field, getattr(facts, attr), role_for, url)

        facts.field_evidence = ev
        return facts

    # --- people (parsed from the SAME fetched pages; no extra requests) ------ #
    def discover_people(self, ctx: CompanyContext, roles: list[str]) -> list[PublicPerson]:
        people: list[PublicPerson] = []
        seen: set[str] = set()
        for _role, url, text in self._fetch_pages(ctx):
            for person in extract_people(text):
                key = (person.full_name or "").strip().lower()
                if not key or key in seen:
                    continue
                seen.add(key)
                people.append(PublicPerson(
                    full_name=person.full_name, job_title=person.job_title,
                    company_name=ctx.company_name, company_domain=ctx.domain,
                    is_current=True, company_match_status=MATCH_VERIFIED,
                    source=self.name, source_label=self.source_label,
                    source_type="company_profile", source_url=url,
                    source_record_id=person.profile_url or url))
        return people

    def discover_public_contacts(self, ctx: CompanyContext) -> list[PublicContact]:
        contacts: list[PublicContact] = []
        seen: set[str] = set()
        for _role, url, text in self._fetch_pages(ctx):
            for c in extract_business_contacts(text, company_domain=ctx.domain):
                if c.value in seen:
                    continue
                seen.add(c.value)
                contacts.append(PublicContact(
                    kind="BUSINESS_EMAIL", value=c.value, source=self.name,
                    source_label=self.source_label, source_type="company_profile", source_url=url))
        return contacts
