"""Free/public intelligence orchestration (Prompt 45).

Runs the enabled public providers ONCE per company opportunity, merges people across
sources by strong identifiers with a documented source priority, computes public
Contact Trust + POC status, and persists real people as DecisionMaker rows with
field-level provenance. Company identity facts (website/country/industry/wikidata_id/
linkedin) are filled from public sources without overwriting existing values.

No fabrication: people/emails/phones/LinkedIn are only ever the values a public source
actually returned; a provider failure never yields fake data (§29). Contact Trust is
kept separate from the business lead score (§31).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Optional

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from config import get_settings
from crm.audit import record_audit
from database.models import (
    Company,
    CompanyFieldEvidence,
    CompanyLocation,
    CompanyOfficer,
    ContactType,
    DataProvenance,
    DecisionMaker,
    EmailStatus,
    Lead,
    PersonMatchStatus,
    RoleCategory,
    VerificationStatus,
)
from integrations.public_intelligence.models import PublicCompanyFacts
from enrichment.contactout_poc import resolve_company_for_lead, _role_category_for  # reuse
from enrichment.stakeholder import recommend_for_lead
from integrations.public_intelligence import (
    CompanyContext,
    PublicPerson,
    build_providers,
)
from integrations.public_intelligence.matching import role_relevance
from integrations.public_intelligence.models import (
    MATCH_LIKELY,
    MATCH_UNKNOWN,
    MATCH_VERIFIED,
    SOURCE_PRIORITY,
    STATUS_STALE,
    STATUS_VERIFIED,
    FieldProvenance,
)
from integrations.public_intelligence.trust import compute_contact_trust, poc_status
from processors.normalization.text import normalize_for_compare
from verification.freshness import compute_freshness

logger = logging.getLogger("integrations.public_intelligence")

# DecisionMaker.source_type values produced by public providers (for cache/dedup scoping).
PUBLIC_SOURCE_TYPES = {"company_profile", "github_public_profile", "wikidata_entity"}
_MATCH_RANK = {MATCH_VERIFIED: 2, MATCH_LIKELY: 1, MATCH_UNKNOWN: 0}
_TRUST_TO_VERIFICATION = {
    STATUS_VERIFIED: VerificationStatus.VERIFIED,
}

# Discovery outcome states.
ST_ENRICHED = "ENRICHED"
ST_CACHED = "CACHED"
ST_NO_POC = "NO_POC_FOUND"
ST_DISABLED = "DISABLED"


@dataclass
class PublicIntelligenceSummary:
    lead_id: Optional[int]
    company_id: Optional[int]
    company_name: Optional[str]
    status: str
    people_found: int = 0
    persisted: int = 0
    provider_status: dict = field(default_factory=dict)   # provider -> status
    company_facts_updated: list[str] = field(default_factory=list)
    reason: str = ""
    pocs: list[DecisionMaker] = field(default_factory=list)


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _context(session: Session, lead: Lead) -> tuple[Optional[Company], CompanyContext]:
    company, company_name, domain = resolve_company_for_lead(session, lead)
    ctx = CompanyContext(
        company_id=company.id if company else None,
        company_name=company_name, normalized_name=(lead.normalized_company_name or ""),
        domain=domain, website=(company.website if company else None),
        linkedin_url=(company.linkedin_url if company else None),
        country=(company.headquarters_country if company else None),
    )
    return company, ctx


def get_public_pocs_for_lead(session: Session, lead: Lead) -> list[DecisionMaker]:
    """Persisted public-source POCs for a lead's company (read path)."""
    company, _, _ = resolve_company_for_lead(session, lead)
    if company is None:
        return []
    rows = session.scalars(select(DecisionMaker).where(
        DecisionMaker.company_id == company.id,
        DecisionMaker.source_type.in_(PUBLIC_SOURCE_TYPES),
        DecisionMaker.full_name.isnot(None),
        DecisionMaker.data_provenance == DataProvenance.REAL,
    )).all()
    return sorted(rows, key=lambda d: (d.match_score or 0, d.contact_trust_score or 0), reverse=True)


def _fresh_cached(session: Session, company_id: int, ttl_hours: int, now: datetime) -> list[DecisionMaker]:
    cutoff = now - timedelta(hours=max(0, ttl_hours))
    rows = session.scalars(select(DecisionMaker).where(
        DecisionMaker.company_id == company_id,
        DecisionMaker.source_type.in_(PUBLIC_SOURCE_TYPES),
        DecisionMaker.full_name.isnot(None),
        DecisionMaker.last_verified_at.isnot(None),
        DecisionMaker.last_verified_at >= cutoff,
    )).all()
    return sorted(rows, key=lambda d: (d.match_score or 0, d.contact_trust_score or 0), reverse=True)


def _dedup_key(p: PublicPerson) -> str:
    """Strong-identifier dedup (§21): LinkedIn > email > provider id > name+company."""
    if p.linkedin_url:
        return f"li:{p.linkedin_url.lower().rstrip('/')}"
    if p.work_email:
        return f"em:{p.work_email.lower()}"
    if p.source_record_id:
        return f"id:{p.source}:{p.source_record_id}"
    return f"nm:{normalize_for_compare(p.full_name)}|{normalize_for_compare(p.company_name)}"


def _merge_people(people: list[PublicPerson]) -> list[PublicPerson]:
    """Merge the same person across providers. Canonical identity fields come from the
    higher-priority source; contact fields fill from whichever source published them.
    Each contributing source is recorded in field_provenance (§18/§20)."""
    ordered = sorted(people, key=lambda p: SOURCE_PRIORITY.get(p.source, 99))
    merged: dict[str, PublicPerson] = {}
    for p in ordered:
        key = _dedup_key(p)
        if key not in merged:
            base = PublicPerson(**{**p.__dict__})
            base.field_provenance = list(p.field_provenance) + [
                FieldProvenance(field="identity", value=p.full_name, source=p.source, source_url=p.source_url)]
            merged[key] = base
            continue
        cur = merged[key]
        # Fill only MISSING contact fields (never overwrite; never fabricate).
        for f in ("work_email", "personal_email", "business_phone", "linkedin_url",
                  "company_domain", "location", "job_title", "department", "seniority", "bio"):
            if not getattr(cur, f) and getattr(p, f):
                setattr(cur, f, getattr(p, f))
        # Upgrade company match to the strongest observed.
        if _MATCH_RANK.get(p.company_match_status, 0) > _MATCH_RANK.get(cur.company_match_status, 0):
            cur.company_match_status = p.company_match_status
        cur.field_provenance.append(
            FieldProvenance(field="corroboration", value=p.full_name, source=p.source, source_url=p.source_url))
    return list(merged.values())


def discover_public_intelligence_for_lead(
    session: Session, lead: Lead, *, providers=None, http: httpx.Client | None = None,
    force: bool = False, actor: str = "SYSTEM", now: Optional[datetime] = None,
) -> PublicIntelligenceSummary:
    now = now or _now()
    settings = get_settings()
    company, ctx = _context(session, lead)
    summary = PublicIntelligenceSummary(lead_id=lead.id, company_id=ctx.company_id,
                                        company_name=ctx.company_name, status=ST_DISABLED)

    if not settings.public_intelligence_active:
        summary.reason = "Public intelligence is disabled."
        return summary

    if ctx.company_id and not force:
        cached = _fresh_cached(session, ctx.company_id, settings.public_intelligence_cache_ttl_hours, now)
        if cached:
            summary.status, summary.pocs = ST_CACHED, cached
            summary.people_found = len(cached)
            summary.reason = f"Reused {len(cached)} recent public POC(s) within the freshness window."
            logger.info("public_intelligence.cache_hit lead_id=%s company_id=%s pocs=%s",
                        lead.id, ctx.company_id, len(cached))
            return summary

    roles = [r.role for r in recommend_for_lead(lead).recommended_roles]
    provider_list = providers if providers is not None else build_providers(http=http)

    all_people: list[PublicPerson] = []
    facts_list: list[PublicCompanyFacts] = []
    for provider in provider_list:
        result = provider.discover(ctx, roles)
        summary.provider_status[provider.name] = result.status
        logger.info("public_intelligence.%s provider=%s records=%s",
                    "success" if result.status == "OK" else result.status.lower(),
                    provider.name, result.records_found)
        all_people.extend(result.people)
        if result.company_facts:
            facts_list.append(result.company_facts)

    # Merge + persist company facts (Company fields + locations + field evidence + trust).
    if company is not None:
        merged_facts = _merge_company_facts(facts_list)
        if merged_facts is not None:
            summary.company_facts_updated = _persist_company_facts(session, company, merged_facts, now)

    merged = _merge_people([p for p in all_people if p.full_name])
    summary.people_found = len(merged)

    persisted = 0
    for person in merged:
        # Only attach as a real POC when the company association is at least LIKELY (§9/§29).
        if person.company_match_status == MATCH_UNKNOWN:
            continue
        dm = _upsert_public_person(session, ctx, person, roles, now)
        if dm is not None:
            summary.pocs.append(dm)
            persisted += 1

    session.commit()
    summary.persisted = persisted
    summary.status = ST_ENRICHED if persisted else ST_NO_POC
    summary.reason = (f"Persisted {persisted} public POC(s)." if persisted
                      else "No verified public POC found; role recommendations only.")
    logger.info("public_intelligence.success lead_id=%s company_id=%s people=%s persisted=%s",
                lead.id, ctx.company_id, len(merged), persisted)
    record_audit(session, entity_type="lead", entity_id=lead.id, action="PUBLIC_INTELLIGENCE_DISCOVER",
                 actor=actor, new_value=str(persisted),
                 reason=f"providers={summary.provider_status} people={len(merged)}", now=now)
    session.commit()
    return summary


@dataclass
class CompanyIntelSummary:
    company_id: int
    company_name: str
    status: str                              # SUCCESS | PARTIAL | SOURCE_UNAVAILABLE | ERROR
    provider_status: dict = field(default_factory=dict)
    fields_updated: list[str] = field(default_factory=list)
    people_persisted: int = 0
    data_trust_score: int = 0
    reason: str = ""


def discover_company_intelligence(
    session: Session, company: Company, *, providers=None, http: httpx.Client | None = None,
    force: bool = False, actor: str = "SYSTEM", now: Optional[datetime] = None,
) -> CompanyIntelSummary:
    """Company-level official intelligence discovery (§26/§39). Runs the official
    company website + Wikidata providers, persists facts/locations/evidence/trust, and
    returns a truthful status. Honours the official-company data freshness window."""
    now = now or _now()
    settings = get_settings()
    summary = CompanyIntelSummary(company_id=company.id, company_name=company.canonical_name,
                                  status="SOURCE_UNAVAILABLE")
    if not settings.public_intelligence_active:
        summary.status, summary.reason = "SOURCE_UNAVAILABLE", "Public intelligence is disabled."
        return summary

    # Freshness cache (§23/§35): skip re-fetch when recently verified.
    ttl = timedelta(days=max(0, settings.official_company_data_ttl_days))
    if not force and company.official_verified_at and (now - company.official_verified_at) < ttl:
        summary.status = "SUCCESS"
        summary.data_trust_score = company.data_trust_score or 0
        summary.reason = "Reused recent official-company data within the freshness window."
        return summary

    ctx = CompanyContext(
        company_id=company.id, company_name=company.canonical_name,
        normalized_name=company.normalized_name, domain=company.primary_domain,
        website=company.website, linkedin_url=company.linkedin_url,
        country=company.headquarters_country)
    wanted = [n for n in ("official_company", "wikidata")
              if settings.public_intelligence_provider_enabled(n)]
    if settings.opencorporates_config_status == "CONFIGURED":
        wanted.append("opencorporates")   # legal-entity verification (§1) when configured
    provider_list = providers if providers is not None else build_providers(names=wanted, http=http)

    facts_list: list[PublicCompanyFacts] = []
    all_people: list[PublicPerson] = []
    for provider in provider_list:
        result = provider.discover(ctx, [])
        summary.provider_status[provider.name] = result.status
        if result.company_facts:
            facts_list.append(result.company_facts)
        all_people.extend(result.people)

    merged = _merge_company_facts(facts_list)
    if merged is not None:
        summary.fields_updated = _persist_company_facts(session, company, merged, now)
    # Persist public leadership discovered from official pages.
    people = _merge_people([p for p in all_people if p.full_name])
    persisted = 0
    for person in people:
        if person.company_match_status == MATCH_UNKNOWN:
            continue
        if _upsert_public_person(session, ctx, person, [], now) is not None:
            persisted += 1
    summary.people_persisted = persisted
    session.commit()

    summary.data_trust_score = company.data_trust_score or 0
    if merged is not None and merged.website:
        # We reached the official site: SUCCESS when an address was found, else PARTIAL.
        summary.status = "SUCCESS" if merged.full_address else "PARTIAL"
        summary.reason = f"Discovered official company facts (trust {summary.data_trust_score})."
    else:
        # No official page could be reached (no domain / all fetches failed) — never faked.
        summary.status = "SOURCE_UNAVAILABLE"
        summary.reason = "Official sources could not be accessed."
    logger.info("official_company.%s company_id=%s fields=%s people=%s trust=%s",
                summary.status.lower(), company.id, len(summary.fields_updated), persisted,
                summary.data_trust_score)
    record_audit(session, entity_type="company", entity_id=company.id,
                 action="OFFICIAL_COMPANY_DISCOVER", actor=actor,
                 new_value=str(len(summary.fields_updated)),
                 reason=f"status={summary.status} providers={summary.provider_status}", now=now)
    session.commit()
    return summary


# --------------------------------------------------------------------------- #
# Company facts: merge across providers + persist (fields + locations + evidence)
# --------------------------------------------------------------------------- #
def _merge_company_facts(facts_list: list[PublicCompanyFacts]) -> Optional[PublicCompanyFacts]:
    """Merge company facts from multiple providers. Official-company facts take
    precedence for overlapping fields; Wikidata fills identity gaps (§20/§22). All
    field-evidence + locations are retained (never dropped)."""
    if not facts_list:
        return None
    # Official first (source priority), then others.
    ordered = sorted(facts_list, key=lambda f: SOURCE_PRIORITY.get(f.source, 99))
    merged = PublicCompanyFacts(source="public_intelligence", source_label="Public sources")
    for f in ordered:
        for attr in ("website", "linkedin_url", "country", "industry", "wikidata_id",
                     "contact_url", "careers_url", "leadership_url", "company_phone",
                     "company_email", "address_line_1", "address_line_2", "city",
                     "state_or_region", "postal_code", "full_address",
                     # OpenCorporates legal identity (distinct from operating brand).
                     "legal_name", "company_number", "jurisdiction_code", "company_status",
                     "incorporation_date", "registry_url", "opencorporates_url",
                     "opencorporates_id", "india_entity_type", "match_status"):
            if not getattr(merged, attr) and getattr(f, attr):
                setattr(merged, attr, getattr(f, attr))
        if merged.registered_location is None and f.registered_location is not None:
            merged.registered_location = f.registered_location
        if f.officers:
            merged.officers.extend(f.officers)
        merged.field_evidence.extend(f.field_evidence)
        merged.locations.extend(f.locations)
        for a in f.aliases:
            if a not in merged.aliases:
                merged.aliases.append(a)
    return merged


def _persist_company_facts(session: Session, company: Company, facts: PublicCompanyFacts,
                           now: datetime) -> list[str]:
    """Persist merged facts: field-level evidence (conflicts retained), canonical
    Company fields (official source wins; retained evidence justifies the value),
    CompanyLocation rows, and the company Data Trust score."""
    from integrations.public_intelligence.official_company.trust import company_data_trust

    updated: list[str] = []

    # 1) Field-level evidence — upsert by (field, source); conflicting sources kept.
    for e in facts.field_evidence:
        if not e.value:
            continue
        existing = session.scalar(select(CompanyFieldEvidence).where(
            CompanyFieldEvidence.company_id == company.id,
            CompanyFieldEvidence.field == e.field, CompanyFieldEvidence.source == e.source))
        row = existing or CompanyFieldEvidence(company_id=company.id, field=e.field, source=e.source)
        row.value, row.source_type, row.source_url = e.value, e.source_type, e.source_url
        row.evidence_text, row.source_priority, row.trust_score = e.evidence_text, e.source_priority, e.trust_score
        row.retrieved_at = row.last_verified_at = now
        row.data_provenance = DataProvenance.REAL
        if existing is None:
            session.add(row)

    # 2) Canonical Company fields. An OFFICIAL company-page source (authoritative) may
    #    overwrite; any other/lower-priority source (e.g. Wikidata) only fills blanks
    #    — existing values are never silently overwritten by weaker evidence (§22).
    official_fields = {e.field for e in facts.field_evidence
                       if (e.source_type or "").startswith("company_")}

    def set_field(attr: str, value: Optional[str], *, official_of: Optional[str] = None,
                  fill_only: bool = False):
        if not value:
            return
        may_overwrite = (not fill_only) and (official_of in official_fields if official_of else True)
        if not may_overwrite and getattr(company, attr, None) not in (None, "", []):
            return
        if getattr(company, attr, None) != value:
            setattr(company, attr, value)
            updated.append(attr)

    set_field("website", facts.website, official_of="website_url")
    set_field("linkedin_url", facts.linkedin_url, official_of="linkedin_url")
    set_field("company_phone", facts.company_phone, official_of="company_phone")
    set_field("company_email", facts.company_email, official_of="company_email")
    set_field("contact_url", facts.contact_url, official_of="contact_url")
    set_field("careers_url", facts.careers_url, official_of="careers_url")
    set_field("leadership_url", facts.leadership_url, official_of="leadership_url")
    set_field("full_address", facts.full_address, official_of="address")
    set_field("postal_code", facts.postal_code, official_of="address")
    set_field("headquarters_city", facts.city, fill_only=True)
    set_field("headquarters_state", facts.state_or_region, fill_only=True)
    set_field("headquarters_country", facts.country, fill_only=True)
    set_field("industry", facts.industry, fill_only=True)
    set_field("wikidata_id", facts.wikidata_id, fill_only=True)

    # 2b) Legal identity (OpenCorporates) — kept DISTINCT from the operating brand;
    #     the registered address never overwrites the operating address (§8/§9/§20).
    set_field("legal_name", facts.legal_name)
    set_field("company_number", facts.company_number)
    set_field("jurisdiction_code", facts.jurisdiction_code)
    set_field("company_status", facts.company_status)
    set_field("incorporation_date", facts.incorporation_date)
    set_field("registry_url", facts.registry_url)
    set_field("opencorporates_url", facts.opencorporates_url)
    set_field("opencorporates_id", facts.opencorporates_id)
    if facts.registered_location and facts.registered_location.full_address:
        set_field("registered_address", facts.registered_location.full_address)
    # India entity type — refine with the company's known India presence (§2).
    if facts.india_entity_type:
        from integrations.public_intelligence.opencorporates.matching import (
            INDIA_ENTITY, INDIA_OFFICE)
        india_type = facts.india_entity_type
        if india_type != INDIA_ENTITY and company.india_presence:
            india_type = INDIA_OFFICE
        set_field("india_entity_type", india_type)

    # 3) Locations (multi-office) — dedup by normalized key; HQ only on evidence.
    #    The OpenCorporates registered office is persisted as a distinct REGISTERED_OFFICE
    #    location — never merged with the operating headquarters (§8/§9/§22).
    all_locations = list(facts.locations)
    if facts.registered_location is not None:
        all_locations.append(facts.registered_location)
    for loc in all_locations:
        key = (loc.full_address or "").lower().strip()
        if not key:
            continue
        existing = session.scalar(select(CompanyLocation).where(
            CompanyLocation.company_id == company.id, CompanyLocation.normalized_key == key))
        if existing is not None:
            existing.last_verified_at = now if hasattr(existing, "last_verified_at") else None
            continue
        session.add(CompanyLocation(
            company_id=company.id, address_line_1=loc.address_line_1, address_line_2=loc.address_line_2,
            city=loc.city, state_or_region=loc.state_or_region, postal_code=loc.postal_code,
            country=loc.country, full_address=loc.full_address, normalized_key=key,
            location_type=loc.location_type, is_headquarters=loc.is_headquarters,
            source=loc.source, source_url=loc.source_url, trust_score=95,
            data_provenance=DataProvenance.REAL, retrieved_at=now))

    # 4) Officers (legal directors) — kept SEPARATE from POCs (§12/§13). Dedup by
    #    (company_id, normalized_name, position). Real, source-backed records only.
    for off in facts.officers:
        name = off.get("name")
        if not name:
            continue
        nkey = normalize_for_compare(name) or None
        pos = off.get("position")
        existing_off = session.scalar(select(CompanyOfficer).where(
            CompanyOfficer.company_id == company.id, CompanyOfficer.normalized_name == nkey,
            CompanyOfficer.position == pos))
        if existing_off is not None:
            continue
        session.add(CompanyOfficer(
            company_id=company.id, name=name, normalized_name=nkey, position=pos,
            start_date=off.get("start_date"), end_date=off.get("end_date"),
            role_kind="LEGAL_OFFICER", source=off.get("source"), source_url=off.get("source_url"),
            data_provenance=DataProvenance.REAL, retrieved_at=now))

    # 5) Company Data Trust (§18) — evidence-based; registry/OpenCorporates add points.
    match_ok = (facts.match_status in ("VERIFIED_MATCH", "LIKELY_MATCH"))
    company.data_trust_score = company_data_trust(
        identity_confirmed=bool(facts.website),
        website_confirmed=bool(facts.website),
        address_confirmed=bool(facts.full_address),
        registry_confirmed=bool(facts.registry_url),
        opencorporates_match=match_ok,
        careers_confirmed=bool(facts.careers_url),
        fresh=True,
    )
    company.official_verified_at = now
    company.last_seen_at = now
    return updated


# --------------------------------------------------------------------------- #
# Person persistence
# --------------------------------------------------------------------------- #
def _match_score(person: PublicPerson, title_rel: int) -> int:
    base = {MATCH_VERIFIED: 60, MATCH_LIKELY: 40, MATCH_UNKNOWN: 10}[person.company_match_status]
    avail = (10 if person.work_email else 0) + (5 if person.business_phone else 0) + (5 if person.linkedin_url else 0)
    return min(100, base + int(title_rel * 0.3) + avail)


def _upsert_public_person(session: Session, ctx: CompanyContext, person: PublicPerson,
                          roles: list[str], now: datetime) -> Optional[DecisionMaker]:
    normalized_name = normalize_for_compare(person.full_name) or None
    if not normalized_name:
        return None
    normalized_role = normalize_for_compare(person.job_title) or None

    title_rel = role_relevance(person.job_title or person.bio, roles)
    trust = compute_contact_trust(
        official_source=(person.source == "official_company"),
        current_company_match=(person.company_match_status == MATCH_VERIFIED),
        current_title_match=bool(title_rel),
        public_business_email=bool(person.work_email),
        public_business_phone=bool(person.business_phone),
    )
    status = poc_status(company_match_status=person.company_match_status, current_title_match=bool(title_rel))
    match_score = _match_score(person, title_rel)

    existing = session.scalar(select(DecisionMaker).where(
        DecisionMaker.company_id == ctx.company_id,
        DecisionMaker.normalized_name == normalized_name,
        DecisionMaker.source_type.in_(PUBLIC_SOURCE_TYPES),
    ))
    fresh = compute_freshness(signal_type="COMPANY", observed_at=now, now=now)
    business_email = person.work_email or None
    email_status = None
    contact_type = ContactType.OTHER
    if business_email:
        email_status = EmailStatus.VERIFIED_SOURCE   # explicitly published on a public source
        contact_type = ContactType.BUSINESS_EMAIL

    target = existing or DecisionMaker(
        company_id=ctx.company_id, company_name=ctx.company_name, normalized_name=normalized_name,
        normalized_role=normalized_role, first_seen_at=now, match_status=PersonMatchStatus.NO_MATCH)
    target.full_name = person.full_name
    target.job_title = person.job_title
    target.role_category = _role_category_for(person.job_title or person.bio)
    target.seniority = person.seniority
    target.geography = person.location
    target.department = person.department
    target.company_domain = ctx.domain or person.company_domain
    if person.linkedin_url:
        target.professional_network_url = person.linkedin_url   # verbatim (§13)
    if business_email:
        target.business_email = business_email
        target.email_status = email_status
        target.contact_type = contact_type
    if person.business_phone:
        target.business_phone = person.business_phone
    target.is_current = person.is_current if person.is_current is not None else True
    target.match_score = match_score
    target.contact_trust_score = trust
    target.contact_trust_status = status
    target.identity_confidence = 85 if (person.full_name and person.job_title) else 55
    target.role_confidence = title_rel
    target.company_confidence = {MATCH_VERIFIED: 90, MATCH_LIKELY: 65, MATCH_UNKNOWN: 30}[person.company_match_status]
    target.contact_confidence = trust
    target.evidence_confidence = 90 if person.source == "official_company" else 60
    target.freshness_score = fresh.score
    target.verification_status = _TRUST_TO_VERIFICATION.get(status, VerificationStatus.PARTIALLY_VERIFIED
                                                            if status == "LIKELY" else VerificationStatus.UNVERIFIED)
    target.contact_source = person.source_label or person.source
    target.source_type = person.source_type
    target.source_url = person.source_url
    target.source_record_id = person.source_record_id
    target.collector_version = "public-intel-1"
    target.data_provenance = DataProvenance.REAL
    target.last_seen_at = now
    target.last_verified_at = now
    # Field-level provenance / corroborating sources (§17/§18/§20).
    refs = target.source_references or []
    for fp in person.field_provenance:
        entry = {"field": fp.field, "source": fp.source, "source_url": fp.source_url,
                 "observed_at": now.isoformat()}
        if entry not in refs:
            refs.append(entry)
    target.source_references = refs
    if existing is None:
        session.add(target)
    return target
