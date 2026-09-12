"""Multi-provider contact-enrichment waterfall (Prompt 49).

Company/opportunity-level (never per job). Credit-aware and lead-priority gated:
public/official sources first, then paid providers in priority order (ContactOut ▸
Apollo ▸ Lusha ▸ Prospeo), with Hunter used for email discovery/verification. Only the
best candidates are enriched. Cross-source evidence + freshness (not provider order)
decide canonical values. A failure never fabricates a person/email/phone — when nothing
is found, callers fall back to a recommended-role-only POC.

Role Match Score (opportunity fit) is kept SEPARATE from Contact Trust and Lead Score.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from config import get_settings
from crm.audit import record_audit
from database.models import (
    ContactType,
    DataProvenance,
    DecisionMaker,
    EmailStatus,
    Lead,
    LeadPriority,
    PersonMatchStatus,
    VerificationStatus,
)
from enrichment.contactout_poc import _role_category_for, resolve_company_for_lead
from enrichment.stakeholder import recommend_for_lead
from integrations.enrichment.base import (
    EnrichedPerson,
    EnrichmentError,
    EnrichmentProvider,
    EnrichmentRateLimited,
)
from integrations.enrichment.registry import build_provider, provider_configured
from integrations.public_intelligence.matching import normalize_company, role_relevance
from processors.normalization.text import normalize_for_compare
from verification.freshness import compute_freshness

logger = logging.getLogger("integrations.enrichment")

# Waterfall order for PAID providers (ContactOut has its own service; this covers the
# additional paid providers). Discovery uses person_search-capable providers first.
_PAID_PRIORITY = ("apollo", "lusha", "prospeo", "hunter")
_SENIOR = ("cto", "cio", "ceo", "chief", "vp", "vice president", "head", "director")


@dataclass
class EnrichmentSummary:
    lead_id: Optional[int]
    company_id: Optional[int]
    company_name: Optional[str]
    status: str                       # ENRICHED | NO_DATA | SKIPPED_LOW_SCORE | NOT_CONFIGURED | ERROR
    provider_status: dict = field(default_factory=dict)
    provider_calls: int = 0
    enrichments: int = 0
    persisted: int = 0
    reason: str = ""
    pocs: list[DecisionMaker] = field(default_factory=list)


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


# --------------------------------------------------------------------------- #
# Scoring — Role Match (opportunity fit) and Contact Trust (§18/§19)
# --------------------------------------------------------------------------- #
def role_match_score(person: EnrichedPerson, roles: list[str], *, company_matched: bool) -> int:
    title_rel = role_relevance(person.job_title, roles)
    text = (person.job_title or "").lower()
    seniority = 100 if any(k in text for k in _SENIOR[:5]) else (85 if any(k in text for k in _SENIOR) else 50)
    current = 100 if person.is_current is not False else 0
    company = 100 if company_matched else 30
    return min(100, int(0.35 * company + 0.30 * title_rel + 0.15 * seniority + 0.20 * current))


def contact_trust(*, official_current_role: bool, current_company: bool, current_title: bool,
                  independent_confirmation: bool, verified_work_email: bool,
                  verified_business_phone: bool) -> int:
    score = 0
    if official_current_role:
        score += 30
    if current_company:
        score += 25
    if current_title:
        score += 20
    if independent_confirmation:
        score += 10
    if verified_work_email:
        score += 10
    if verified_business_phone:
        score += 5
    return min(100, score)


# --------------------------------------------------------------------------- #
# Waterfall
# --------------------------------------------------------------------------- #
def _paid_providers(providers, http=None) -> list[EnrichmentProvider]:
    if providers is not None:
        return providers
    return [p for p in (build_provider(n, http=http) for n in _PAID_PRIORITY
                        if provider_configured(n)) if p is not None]


def enrich_lead_contacts(session: Session, lead: Lead, *, providers=None, force: bool = False,
                         actor: str = "SYSTEM", now: Optional[datetime] = None) -> EnrichmentSummary:
    now = now or _now()
    settings = get_settings()
    company, company_name, domain = resolve_company_for_lead(session, lead)
    summary = EnrichmentSummary(lead_id=lead.id, company_id=(company.id if company else None),
                                company_name=company_name, status="NO_DATA")

    provider_list = _paid_providers(providers, http=None)
    if not provider_list:
        summary.status = "NOT_CONFIGURED"
        summary.reason = "No paid enrichment provider configured."
        return summary

    # Lead-priority gating (§29): only HOT/WARM (or >= min score) get paid enrichment.
    score = float(lead.lead_score or 0)
    hot_warm = lead.lead_priority in (LeadPriority.HOT, LeadPriority.WARM)
    if not force and not hot_warm and score < settings.enrichment_min_lead_score:
        summary.status = "SKIPPED_LOW_SCORE"
        summary.reason = f"Lead score {score:.0f} below enrichment threshold; public sources only."
        return summary

    roles = [r.role for r in recommend_for_lead(lead).recommended_roles]
    max_calls = max(1, settings.max_provider_calls_per_opportunity)
    max_enrich = max(0, settings.max_contact_enrichments_per_opportunity)

    # Step 1 — candidate discovery via the first configured person_search provider.
    candidates: list[EnrichedPerson] = []
    for p in provider_list:
        if summary.provider_calls >= max_calls:
            break
        if not p.capabilities.person_search and not p.capabilities.decision_maker_search:
            continue
        try:
            found = p.search_people(company_name=company_name, titles=roles[:5], domain=domain)
            summary.provider_calls += 1
            summary.provider_status[p.name] = "SUCCESS" if found else "NO_DATA"
            candidates.extend(found)
            if found:
                break   # primary discovery succeeded
        except EnrichmentRateLimited:
            summary.provider_status[p.name] = "RATE_LIMITED"
        except EnrichmentError:
            summary.provider_status[p.name] = "SOURCE_UNAVAILABLE"

    if not candidates:
        summary.status = "NO_DATA"
        summary.reason = "No candidates from paid providers; use public sources / recommended role."
        _audit(session, lead, summary, actor, now)
        return summary

    # Step 2 — rank; keep company-matched candidates.
    tgt = normalize_company(company_name)
    def matched(c: EnrichedPerson) -> bool:
        return bool(tgt) and normalize_company(c.company_name) == tgt if c.company_name else False
    ranked = sorted(
        [(c, role_match_score(c, roles, company_matched=matched(c))) for c in candidates if c.full_name],
        key=lambda t: t[1], reverse=True)

    # Step 3 — enrich the best few missing contact info (credit-capped) + Hunter verify.
    enrich_providers = [p for p in provider_list if p.capabilities.person_enrichment or p.capabilities.email_finder]
    hunter = next((p for p in provider_list if p.name == "hunter"), None)
    persisted = 0
    for person, rms in ranked:
        if persisted >= max_enrich:
            break
        needs_contact = not (person.work_email and person.work_email.email) and not (person.phone and person.phone.number)
        if needs_contact and summary.enrichments < max_enrich:
            for ep in enrich_providers:
                if summary.provider_calls >= max_calls:
                    break
                try:
                    if ep.name == "hunter" and person.full_name and domain:
                        er = ep.find_business_email(full_name=person.full_name, domain=domain)
                        if er and er.email:
                            person.work_email = er
                    elif ep.capabilities.person_enrichment:
                        enriched = ep.enrich_person(full_name=person.full_name, linkedin_url=person.linkedin_url,
                                                    company_name=company_name, domain=domain)
                        if enriched:
                            _merge_contact(person, enriched)
                    summary.provider_calls += 1
                    summary.enrichments += 1
                    summary.provider_status.setdefault(ep.name, "SUCCESS")
                    if person.work_email and person.work_email.email:
                        break
                except EnrichmentError:
                    summary.provider_status[ep.name] = "SOURCE_UNAVAILABLE"
        # Verify a work email with Hunter when possible (preserve provider status verbatim).
        if hunter and person.work_email and person.work_email.email and \
           person.work_email.verification_status in ("UNVERIFIED", "UNKNOWN") and summary.provider_calls < max_calls:
            try:
                v = hunter.verify_email(person.work_email.email)
                summary.provider_calls += 1
                if v:
                    person.work_email.verification_status = v.verification_status
            except EnrichmentError:
                pass
        dm = _persist_poc(session, company_id=summary.company_id, company_name=company_name,
                          domain=domain, person=person, roles=roles, role_match=rms,
                          company_matched=matched(person), now=now)
        if dm is not None:
            summary.pocs.append(dm)
            persisted += 1

    session.commit()
    summary.persisted = persisted
    summary.status = "ENRICHED" if persisted else "NO_DATA"
    summary.reason = f"Enriched {persisted} POC(s) across {len(summary.provider_status)} provider(s)."
    logger.info("enrichment.person_enriched lead_id=%s persisted=%s calls=%s", lead.id, persisted, summary.provider_calls)
    _audit(session, lead, summary, actor, now)
    return summary


def _merge_contact(target: EnrichedPerson, other: EnrichedPerson) -> None:
    if (not target.work_email or not target.work_email.email) and other.work_email and other.work_email.email:
        target.work_email = other.work_email
    if (not target.phone or not target.phone.number) and other.phone and other.phone.number:
        target.phone = other.phone
    if not target.linkedin_url and other.linkedin_url:
        target.linkedin_url = other.linkedin_url


def _persist_poc(session, *, company_id, company_name, domain, person: EnrichedPerson,
                 roles, role_match, company_matched, now) -> Optional[DecisionMaker]:
    normalized_name = normalize_for_compare(person.full_name) or None
    if not normalized_name:
        return None
    normalized_role = normalize_for_compare(person.job_title) or None
    email = person.work_email.email if person.work_email else None
    email_vs = person.work_email.verification_status if person.work_email else None
    phone = person.phone.number if person.phone else None

    existing = session.scalar(select(DecisionMaker).where(
        DecisionMaker.company_id == company_id, DecisionMaker.normalized_name == normalized_name,
        DecisionMaker.contact_source == person.source_label))
    title_rel = role_relevance(person.job_title, roles)
    trust = contact_trust(
        official_current_role=False, current_company=company_matched,
        current_title=bool(title_rel), independent_confirmation=False,
        verified_work_email=(email_vs == "VALID"), verified_business_phone=bool(phone))
    fresh = compute_freshness(signal_type="COMPANY", observed_at=now, now=now)

    target = existing or DecisionMaker(company_id=company_id, company_name=company_name,
                                       normalized_name=normalized_name, normalized_role=normalized_role,
                                       first_seen_at=now, match_status=PersonMatchStatus.NO_MATCH)
    target.full_name = person.full_name
    target.job_title = person.job_title
    target.role_category = _role_category_for(person.job_title)
    target.company_domain = domain or person.company_domain
    if person.linkedin_url:
        target.professional_network_url = person.linkedin_url
    if email:
        target.business_email = email
        target.email_status = EmailStatus.VERIFIED_SOURCE if email_vs == "VALID" else EmailStatus.UNVERIFIED_SOURCE
        target.contact_type = ContactType.BUSINESS_EMAIL
        target.email_verification_status = email_vs
    if phone:
        target.business_phone = phone
        target.phone_type = person.phone.phone_type if person.phone else "UNKNOWN"
        target.phone_verification_status = person.phone.verification_status if person.phone else None
    target.is_current = person.is_current if person.is_current is not None else True
    target.employment_status = "CURRENT_LIKELY" if company_matched else "UNKNOWN"
    target.role_match_score = role_match
    target.match_score = role_match
    target.contact_trust_score = trust
    target.contact_trust_status = "VERIFIED" if trust >= 80 else ("LIKELY" if company_matched else "UNVERIFIED")
    target.company_confidence = 90 if company_matched else 40
    target.contact_confidence = trust
    target.evidence_confidence = 65   # paid provider (not the company's own source)
    target.freshness_score = fresh.score
    target.verification_status = VerificationStatus.PARTIALLY_VERIFIED if company_matched else VerificationStatus.UNVERIFIED
    target.contact_source = person.source_label
    target.source_type = "contact_enrichment"
    target.source_url = person.source_url
    target.source_record_id = person.provider_person_id
    target.collector_version = f"{person.source}-enrich-1"
    target.data_provenance = DataProvenance.REAL
    target.last_seen_at = now
    target.last_verified_at = now
    ref = {"source": person.source_label, "source_url": person.source_url,
           "field": "enrichment", "observed_at": now.isoformat()}
    refs = target.source_references or []
    if ref not in refs:
        target.source_references = refs + [ref]
    if existing is None:
        session.add(target)
    return target


def _audit(session, lead, summary, actor, now) -> None:
    record_audit(session, entity_type="lead", entity_id=lead.id, action="CONTACT_ENRICHMENT",
                 actor=actor, new_value=str(summary.persisted),
                 reason=f"status={summary.status} providers={summary.provider_status} calls={summary.provider_calls}",
                 now=now)
    session.commit()
