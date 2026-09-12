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
    ContactType,
    DataProvenance,
    DecisionMaker,
    EmailStatus,
    Lead,
    PersonMatchStatus,
    RoleCategory,
    VerificationStatus,
)
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
    best_facts_by_field: dict[str, tuple[int, str, Optional[str], Optional[str]]] = {}
    for provider in provider_list:
        result = provider.discover(ctx, roles)
        summary.provider_status[provider.name] = result.status
        logger.info("public_intelligence.%s provider=%s records=%s",
                    "success" if result.status == "OK" else result.status.lower(),
                    provider.name, result.records_found)
        all_people.extend(result.people)
        if result.company_facts:
            _collect_company_facts(result.company_facts, provider.name, best_facts_by_field)

    # Merge company facts into the Company (fill blanks only; never overwrite; §20).
    if company is not None:
        summary.company_facts_updated = _apply_company_facts(company, best_facts_by_field, now)

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


# --------------------------------------------------------------------------- #
# Company facts
# --------------------------------------------------------------------------- #
def _collect_company_facts(facts, provider_name, best: dict) -> None:
    rank = SOURCE_PRIORITY.get(provider_name, 99)
    for fname, value in (("website", facts.website), ("linkedin_url", facts.linkedin_url),
                         ("headquarters_country", facts.country), ("industry", facts.industry),
                         ("wikidata_id", facts.wikidata_id)):
        if not value:
            continue
        cur = best.get(fname)
        if cur is None or rank < cur[0]:
            best[fname] = (rank, provider_name, value, facts.source_url)


def _apply_company_facts(company: Company, best: dict, now: datetime) -> list[str]:
    updated: list[str] = []
    for fname, (_, _prov, value, _url) in best.items():
        # Fill only when the canonical field is currently empty (never silently overwrite).
        if getattr(company, fname, None) in (None, "", []):
            setattr(company, fname, value)
            updated.append(fname)
    if updated:
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
