"""Company-level POC discovery + enrichment via ContactOut (Prompt 44).

Runs ONCE per company-level opportunity (never once per job): resolve the company →
recommended POC roles (deterministic, from the real opportunity) → ContactOut
Decision Makers → optional targeted People Search → rank → validate current
employment → optionally enrich the best few → persist as DecisionMaker rows with
full ContactOut provenance.

Credit-aware (§28): capped searches + enrichments per opportunity. Cache-aware
(§29): recent verified ContactOut POCs are reused instead of spending a credit.
Never fabricates: a person is attached only when ContactOut returns them AND their
current company is validated; missing contact fields stay empty.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from company.normalization import normalize_name as normalize_company
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
from enrichment.stakeholder import recommend_for_lead
from integrations.contactout import (
    ContactOutClient,
    ContactOutError,
    ContactOutNotConfigured,
    ContactOutRateLimitError,
    parse_enrich,
    parse_people,
)
from integrations.contactout.models import ContactOutPerson
from integrations.contactout.ranking import (
    TRUST_LIKELY,
    TRUST_NO_CONTACT_DATA,
    TRUST_VERIFIED,
    POCRanking,
    rank_person,
)
from processors.normalization.text import normalize_for_compare
from verification.freshness import compute_freshness

logger = logging.getLogger("integrations.contactout")

CONTACT_SOURCE = "ContactOut"
SOURCE_TYPE = "contact_enrichment"
COLLECTOR_VERSION = "contactout-1"
_EVIDENCE_CONFIDENCE = 70   # real third-party provider (not the company's own source)

# Discovery outcome states (honest — never "fake POC generated").
ST_ENRICHED = "ENRICHED"
ST_CACHED = "CACHED"
ST_NO_POC = "NO_POC_FOUND"
ST_NOT_CONFIGURED = "NOT_CONFIGURED"
ST_UNAVAILABLE = "UNAVAILABLE"
ST_RATE_LIMITED = "RATE_LIMITED"

_TRUST_TO_VERIFICATION = {
    TRUST_VERIFIED: VerificationStatus.VERIFIED,
    TRUST_LIKELY: VerificationStatus.PARTIALLY_VERIFIED,
}

# Light title → role-category mapping (for filtering/UX; job_title is authoritative).
_ROLE_KEYWORDS = (
    (("cto", "cio", "chief", "vp eng", "vice president"), RoleCategory.TECHNICAL),
    (("engineering", "engineer", "developer", "software", "cloud", "infrastructure", "ai", "data"),
     RoleCategory.ENGINEERING),
    (("talent", "recruit", "recruiting", "recruitment"), RoleCategory.TALENT_ACQUISITION),
    (("procurement", "sourcing"), RoleCategory.PROCUREMENT),
    (("vendor",), RoleCategory.VENDOR_MANAGEMENT),
    (("delivery", "program", "project"), RoleCategory.DELIVERY),
)


@dataclass
class PocDiscoverySummary:
    lead_id: Optional[int]
    company_id: Optional[int]
    company_name: Optional[str]
    status: str
    candidates_found: int = 0
    searches_used: int = 0
    enrichments_used: int = 0
    persisted: int = 0
    reason: str = ""
    error_code: Optional[str] = None
    pocs: list[DecisionMaker] = field(default_factory=list)


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _role_category_for(title: Optional[str]) -> RoleCategory:
    t = (title or "").lower()
    for keywords, category in _ROLE_KEYWORDS:
        if any(k in t for k in keywords):
            return category
    return RoleCategory.OTHER


def resolve_company_for_lead(session: Session, lead: Lead) -> tuple[Optional[Company], str, Optional[str]]:
    """Resolve the Company entity + identifiers for a lead. Returns
    (company_or_None, company_name, company_domain). Company name is always available
    (from the lead); domain only when a real one is known — never invented."""
    name = lead.company_name or ""
    norm = lead.normalized_company_name or normalize_company(name).normalized_name
    company = session.scalar(select(Company).where(Company.normalized_name == norm)) if norm else None
    domain = (company.primary_domain if company else None) or None
    return company, (company.canonical_name if company else name), domain


def _recommended_role_names(lead: Lead) -> list[str]:
    """Ordered recommended POC role names for the opportunity (deterministic, §6)."""
    rec = recommend_for_lead(lead)
    return [r.role for r in rec.recommended_roles]


def get_pocs_for_lead(session: Session, lead: Lead, *, provenance: DataProvenance = DataProvenance.REAL) -> list[DecisionMaker]:
    """Existing ContactOut-sourced POCs for a lead's company (read path). People only,
    ranked by match then trust. No API call, no fabrication."""
    company, _, _ = resolve_company_for_lead(session, lead)
    if company is None:
        return []
    rows = session.scalars(select(DecisionMaker).where(
        DecisionMaker.company_id == company.id,
        DecisionMaker.contact_source == CONTACT_SOURCE,
        DecisionMaker.full_name.isnot(None),
        DecisionMaker.data_provenance == provenance,
    )).all()
    return sorted(rows, key=lambda d: (d.match_score or 0, d.contact_trust_score or 0), reverse=True)


def _fresh_cached_pocs(session: Session, company_id: int, ttl_hours: int, now: datetime) -> list[DecisionMaker]:
    cutoff = now - timedelta(hours=max(0, ttl_hours))
    rows = session.scalars(select(DecisionMaker).where(
        DecisionMaker.company_id == company_id,
        DecisionMaker.contact_source == CONTACT_SOURCE,
        DecisionMaker.full_name.isnot(None),
        DecisionMaker.last_verified_at.isnot(None),
        DecisionMaker.last_verified_at >= cutoff,
    )).all()
    return sorted(rows, key=lambda d: (d.match_score or 0, d.contact_trust_score or 0), reverse=True)


def discover_pocs_for_lead(
    session: Session, lead: Lead, *, client: Optional[ContactOutClient] = None,
    force: bool = False, actor: str = "SYSTEM", now: Optional[datetime] = None,
) -> PocDiscoverySummary:
    """Discover + persist real POCs for a lead's company via ContactOut."""
    now = now or _now()
    settings = get_settings()
    company, company_name, company_domain = resolve_company_for_lead(session, lead)
    company_id = company.id if company else None
    summary = PocDiscoverySummary(lead_id=lead.id, company_id=company_id, company_name=company_name,
                                  status=ST_NOT_CONFIGURED)

    if settings.contactout_config_status != "CONFIGURED":
        summary.reason = "ContactOut is not configured; POC enrichment unavailable."
        logger.info("contactout.skip lead_id=%s reason=not_configured", lead.id)
        return summary

    # Cache reuse (§29) — do not spend a credit when fresh POCs already exist.
    if company_id and not force:
        cached = _fresh_cached_pocs(session, company_id, settings.contactout_cache_ttl_hours, now)
        if cached:
            summary.status = ST_CACHED
            summary.pocs = cached
            summary.persisted = 0
            summary.candidates_found = len(cached)
            summary.reason = f"Reused {len(cached)} recent ContactOut POC(s) within the freshness window."
            logger.info("contactout.cache_hit lead_id=%s company_id=%s pocs=%s", lead.id, company_id, len(cached))
            return summary

    client = client or ContactOutClient()
    roles = _recommended_role_names(lead)
    max_searches = max(1, settings.contactout_max_poc_searches_per_opportunity)
    max_enrich = max(0, settings.contactout_max_enrichments_per_opportunity)

    candidates: list[ContactOutPerson] = []
    try:
        # Step 1 — Decision Makers (primary company-level discovery).
        dm_raw = client.get_decision_makers(domain=company_domain, name=None if company_domain else company_name)
        summary.searches_used += 1
        candidates.extend(parse_people(dm_raw, endpoint="decision-makers").people)
        logger.info("contactout.request lead_id=%s endpoint=decision-makers candidates=%s", lead.id, len(candidates))

        # Step 2 — targeted People Search when decision-makers are insufficient.
        matched = [p for p in candidates if _is_company_match(p, company_name, company_domain)]
        role_idx = 0
        while not matched and roles and summary.searches_used < max_searches and role_idx < len(roles):
            title = roles[role_idx]
            role_idx += 1
            ps_raw = client.search_people(job_title=[title], company=company_name,
                                          current_titles_only=True, page=1, page_size=25)
            summary.searches_used += 1
            new = parse_people(ps_raw, endpoint="people-search").people
            candidates.extend(new)
            matched = [p for p in candidates if _is_company_match(p, company_name, company_domain)]
            logger.info("contactout.request lead_id=%s endpoint=people-search title=%r candidates=%s",
                        lead.id, title, len(new))
    except ContactOutNotConfigured:
        summary.status = ST_NOT_CONFIGURED
        summary.reason = "ContactOut is not configured; POC enrichment unavailable."
        return summary
    except ContactOutRateLimitError as exc:
        summary.status, summary.error_code = ST_RATE_LIMITED, "rate_limited"
        summary.reason = "ContactOut rate limit reached; POC discovery unavailable right now."
        logger.warning("contactout.rate_limited lead_id=%s", lead.id)
        _audit(session, lead, company_id, actor, summary, now)
        return summary
    except ContactOutError as exc:
        summary.status, summary.error_code = ST_UNAVAILABLE, "error"
        summary.reason = "ContactOut is unavailable; POC discovery could not run."
        logger.warning("contactout.error lead_id=%s reason=%s", lead.id, type(exc).__name__)
        _audit(session, lead, company_id, actor, summary, now)
        return summary

    summary.candidates_found = len(candidates)

    # Rank + keep only candidates whose CURRENT company is validated (§18).
    ranked: list[tuple[ContactOutPerson, POCRanking]] = []
    seen: set[str] = set()
    for p in candidates:
        key = (p.linkedin_url or p.contactout_id or f"{p.full_name}|{p.job_title}" or "").lower()
        if not p.full_name or key in seen:
            continue
        seen.add(key)
        r = rank_person(p, target_name=company_name, target_domain=company_domain, recommended_roles=roles)
        if r.company_matched:
            ranked.append((p, r))
    ranked.sort(key=lambda pr: pr[1].match_score, reverse=True)

    if not ranked:
        summary.status = ST_NO_POC
        summary.reason = "No verified POC found for this opportunity."
        logger.info("contactout.empty lead_id=%s company_id=%s", lead.id, company_id)
        _audit(session, lead, company_id, actor, summary, now)
        return summary

    # Step — enrich only the best few that lack a business contact (credit cap §28).
    for person, _r in ranked:
        if summary.enrichments_used >= max_enrich:
            break
        if person.work_email or person.phone:
            continue
        if not (person.linkedin_url or (person.full_name and (company_domain or company_name))):
            continue
        try:
            enr_raw = client.enrich_person(
                linkedin_url=person.linkedin_url, full_name=person.full_name,
                company=company_name, company_domain=company_domain, job_title=person.job_title)
            summary.enrichments_used += 1
            enriched = parse_enrich(enr_raw)
            if enriched:
                _merge_contact(person, enriched)
            logger.info("contactout.enrichment lead_id=%s enriched=%s", lead.id, bool(enriched))
        except ContactOutError as exc:
            logger.warning("contactout.error lead_id=%s endpoint=enrich reason=%s", lead.id, type(exc).__name__)
            break  # stop enriching on provider error; keep what we have

    # Persist as DecisionMaker rows (re-rank after enrichment so trust reflects new contact data).
    persisted = 0
    for person, _r in ranked:
        ranking = rank_person(person, target_name=company_name, target_domain=company_domain,
                              recommended_roles=roles)
        dm = _upsert_poc(session, company_id=company_id, company_name=company_name,
                         company_domain=company_domain, person=person, ranking=ranking, now=now)
        if dm is not None:
            summary.pocs.append(dm)
            persisted += 1
    session.commit()
    summary.persisted = persisted
    summary.status = ST_ENRICHED
    summary.reason = f"Persisted {persisted} real POC(s) from ContactOut."
    logger.info("contactout.success lead_id=%s company_id=%s persisted=%s searches=%s enrich=%s",
                lead.id, company_id, persisted, summary.searches_used, summary.enrichments_used)
    _audit(session, lead, company_id, actor, summary, now)
    return summary


def enrich_poc(session: Session, dm: DecisionMaker, *, client: Optional[ContactOutClient] = None,
               actor: str = "SYSTEM", now: Optional[datetime] = None) -> PocDiscoverySummary:
    """Re-enrich a single stored POC (POST /pocs/{id}/enrich). Real identifiers only."""
    now = now or _now()
    settings = get_settings()
    summary = PocDiscoverySummary(lead_id=None, company_id=dm.company_id, company_name=dm.company_name,
                                  status=ST_NOT_CONFIGURED)
    if settings.contactout_config_status != "CONFIGURED":
        summary.reason = "ContactOut is not configured; enrichment unavailable."
        return summary
    if not (dm.professional_network_url or dm.full_name):
        summary.status, summary.reason = ST_NO_POC, "POC has no identifiers to enrich."
        return summary
    client = client or ContactOutClient()
    try:
        raw = client.enrich_person(
            linkedin_url=dm.professional_network_url, full_name=dm.full_name,
            company=dm.company_name, company_domain=dm.company_domain, job_title=dm.job_title)
        summary.enrichments_used = 1
        enriched = parse_enrich(raw)
    except ContactOutRateLimitError:
        summary.status, summary.error_code, summary.reason = ST_RATE_LIMITED, "rate_limited", "ContactOut rate limit reached."
        return summary
    except ContactOutError:
        summary.status, summary.error_code, summary.reason = ST_UNAVAILABLE, "error", "ContactOut unavailable."
        return summary
    if not enriched:
        summary.status, summary.reason = ST_NO_POC, "ContactOut returned no additional data."
        _audit_poc(session, dm, actor, summary, now)
        return summary
    # Merge new real contact info; never overwrite a value with an empty one.
    if enriched.work_email and not dm.business_email:
        dm.business_email = enriched.work_email
        dm.email_status = EmailStatus.VERIFIED_SOURCE if enriched.work_email_verified else EmailStatus.UNVERIFIED_SOURCE
        dm.contact_type = ContactType.BUSINESS_EMAIL
    if enriched.phone and not dm.business_phone:
        dm.business_phone = enriched.phone
    if enriched.linkedin_url and not dm.professional_network_url:
        dm.professional_network_url = enriched.linkedin_url
    dm.last_seen_at = now
    dm.last_verified_at = now
    session.commit()
    summary.status, summary.persisted, summary.pocs = ST_ENRICHED, 1, [dm]
    summary.reason = "POC re-enriched from ContactOut."
    _audit_poc(session, dm, actor, summary, now)
    return summary


# --------------------------------------------------------------------------- #
# Internals
# --------------------------------------------------------------------------- #
def _is_company_match(person: ContactOutPerson, name: Optional[str], domain: Optional[str]) -> bool:
    from integrations.contactout.ranking import validate_company_match
    matched, _, _ = validate_company_match(person, target_name=name, target_domain=domain)
    return matched


def _merge_contact(target: ContactOutPerson, enriched: ContactOutPerson) -> None:
    """Fill only MISSING contact fields from an enrich result — never fabricate."""
    if not target.work_email and enriched.work_email:
        target.work_email = enriched.work_email
        target.work_email_verified = enriched.work_email_verified
        target.availability.work_email = True
    if not target.phone and enriched.phone:
        target.phone = enriched.phone
        target.availability.phone = True
    if not target.linkedin_url and enriched.linkedin_url:
        target.linkedin_url = enriched.linkedin_url


def _upsert_poc(session: Session, *, company_id: Optional[int], company_name: Optional[str],
                company_domain: Optional[str], person: ContactOutPerson, ranking: POCRanking,
                now: datetime) -> Optional[DecisionMaker]:
    normalized_name = normalize_for_compare(person.full_name) or None
    normalized_role = normalize_for_compare(person.job_title) or None
    if not normalized_name:
        return None

    existing = session.scalar(select(DecisionMaker).where(
        DecisionMaker.company_id == company_id,
        DecisionMaker.normalized_name == normalized_name,
        DecisionMaker.contact_source == CONTACT_SOURCE,
    ))

    # Business contact fields — work email only (never personal as business, §11/§19).
    business_email = person.work_email or None
    email_status = None
    contact_type = ContactType.OTHER
    if business_email:
        email_status = EmailStatus.VERIFIED_SOURCE if person.work_email_verified else EmailStatus.UNVERIFIED_SOURCE
        contact_type = ContactType.BUSINESS_EMAIL

    verification = _TRUST_TO_VERIFICATION.get(ranking.trust_status, VerificationStatus.UNVERIFIED)
    fresh = compute_freshness(signal_type="COMPANY", observed_at=now, now=now)
    identity = 85 if (person.full_name and person.job_title) else (55 if person.full_name else 0)
    ref = {"source": CONTACT_SOURCE, "source_url": person.linkedin_url,
           "source_record_id": person.contactout_id, "observed_at": now.isoformat()}

    target = existing or DecisionMaker(company_id=company_id, company_name=company_name,
                                       normalized_name=normalized_name, normalized_role=normalized_role,
                                       first_seen_at=now, match_status=PersonMatchStatus.NO_MATCH)
    target.full_name = person.full_name
    target.job_title = person.job_title
    target.role_category = _role_category_for(person.job_title)
    target.seniority = person.seniority
    target.geography = person.location
    target.company_domain = company_domain or person.company_domain
    target.professional_network_url = person.linkedin_url   # verbatim, never modified (§13)
    if business_email:
        target.business_email = business_email
        target.email_status = email_status
        target.contact_type = contact_type
    if person.phone:
        target.business_phone = person.phone   # only a real returned number (§12)
    target.is_current = person.is_current if person.is_current is not None else True
    target.match_score = ranking.match_score
    target.contact_trust_score = ranking.trust_score
    target.contact_trust_status = ranking.trust_status
    target.identity_confidence = identity
    target.role_confidence = ranking.title_relevance
    target.company_confidence = ranking.company_match_confidence
    target.contact_confidence = ranking.trust_score
    target.evidence_confidence = _EVIDENCE_CONFIDENCE
    target.freshness_score = fresh.score
    target.verification_status = verification
    target.contact_source = CONTACT_SOURCE
    target.source_type = SOURCE_TYPE
    target.source_url = person.linkedin_url
    target.source_record_id = person.contactout_id
    target.collector_version = COLLECTOR_VERSION
    target.data_provenance = DataProvenance.REAL
    target.last_seen_at = now
    target.last_verified_at = now
    refs = target.source_references or []
    if not any(r.get("source_record_id") == person.contactout_id for r in refs):
        target.source_references = refs + [ref]
    if existing is None:
        session.add(target)
    return target


def _audit(session: Session, lead: Lead, company_id: Optional[int], actor: str,
           summary: PocDiscoverySummary, now: datetime) -> None:
    record_audit(
        session, entity_type="lead", entity_id=lead.id, action="CONTACTOUT_DISCOVER",
        actor=actor, new_value=str(summary.persisted),
        reason=(f"status={summary.status} candidates={summary.candidates_found} "
                f"searches={summary.searches_used} enrich={summary.enrichments_used}"),
        source=CONTACT_SOURCE, now=now,
    )
    session.commit()


def _audit_poc(session: Session, dm: DecisionMaker, actor: str, summary: PocDiscoverySummary,
               now: datetime) -> None:
    record_audit(
        session, entity_type="decision_maker", entity_id=dm.id, action="CONTACTOUT_ENRICH",
        actor=actor, new_value=str(summary.persisted), reason=f"status={summary.status}",
        source=CONTACT_SOURCE, now=now,
    )
    session.commit()
