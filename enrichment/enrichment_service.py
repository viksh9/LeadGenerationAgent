"""Persist real people / business contacts with resolution, verification, freshness.

Turns an OfficialCompanySourceEnricher result into DecisionMaker rows with:
  * deterministic person resolution (name alone never merges distinct people),
  * distinct confidence axes (identity / role / company / contact / evidence),
  * verification status + freshness (reusing the evidence/freshness rules),
  * mandatory provenance (REAL) and idempotent upsert (history preserved).

Never fabricates. Rows are created only from what the enricher actually extracted.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from config.evidence import SOURCE_TIER_BY_ID, TIER_RELIABILITY
from database.models import (
    Company,
    ContactType,
    DataProvenance,
    DecisionMaker,
    PersonMatchStatus,
    RoleCategory,
    SourceTier,
    VerificationStatus,
)
from enrichment.person_enricher import OfficialCompanySourceEnricher
from verification.freshness import compute_freshness

logger = logging.getLogger("enrichment")

_OFFICIAL_TIER = SourceTier.TIER_1     # official company source


@dataclass
class EnrichmentRunSummary:
    company_id: Optional[int]
    provider: str
    people_found: int = 0
    contacts_found: int = 0
    people_accepted: int = 0
    contacts_accepted: int = 0
    duplicates: int = 0
    rejected: int = 0
    pages_fetched: int = 0
    errors: list[str] = field(default_factory=list)


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def resolve_person(session: Session, *, company_id: Optional[int], normalized_name: Optional[str],
                   normalized_role: Optional[str]) -> tuple[Optional[DecisionMaker], PersonMatchStatus]:
    """Deterministic person resolution. Name alone never yields a merge."""
    if not normalized_name:
        return None, PersonMatchStatus.NO_MATCH
    exact = session.scalar(select(DecisionMaker).where(
        DecisionMaker.company_id == company_id,
        DecisionMaker.normalized_name == normalized_name,
        DecisionMaker.normalized_role == normalized_role,
    ))
    if exact is not None:
        return exact, PersonMatchStatus.EXACT_MATCH
    same_person = session.scalar(select(DecisionMaker).where(
        DecisionMaker.company_id == company_id,
        DecisionMaker.normalized_name == normalized_name,
    ))
    if same_person is not None:
        # Same person at same company, different observed role → keep separate but flag.
        return same_person, PersonMatchStatus.REVIEW_REQUIRED
    return None, PersonMatchStatus.NO_MATCH


def _evidence_confidence(source_type: Optional[str]) -> int:
    tier = _OFFICIAL_TIER if source_type == "OFFICIAL_COMPANY" else SOURCE_TIER_BY_ID.get(
        (source_type or "").lower(), SourceTier.TIER_4)
    return TIER_RELIABILITY[tier]


def _person_confidences(p: dict, *, company_domain: Optional[str]) -> dict:
    on_domain = bool(company_domain and (p.get("source_url") or "").lower().find(company_domain.lower()) >= 0)
    identity = 85 if (p.get("full_name") and p.get("job_title")) else (55 if p.get("full_name") else 0)
    role = 85 if p.get("normalized_role") and p.get("role_category") != RoleCategory.OTHER else (
        60 if p.get("job_title") else 30)
    company = 90 if on_domain else 65
    return {"identity_confidence": identity, "role_confidence": role,
            "company_confidence": company, "evidence_confidence": _evidence_confidence(p.get("source_type"))}


def _verification(identity: int, role: int, company: int, fresh_stale: bool) -> VerificationStatus:
    if fresh_stale:
        return VerificationStatus.STALE
    if identity >= 80 and role >= 70 and company >= 80:
        return VerificationStatus.VERIFIED
    if identity >= 50 and company >= 60:
        return VerificationStatus.PARTIALLY_VERIFIED
    return VerificationStatus.UNVERIFIED


def enrich_company(session: Session, company: Company, *,
                   enricher: Optional[OfficialCompanySourceEnricher] = None,
                   provenance: DataProvenance = DataProvenance.REAL) -> EnrichmentRunSummary:
    """Run official-source enrichment for one company and persist real records."""
    enricher = enricher or OfficialCompanySourceEnricher()
    summary = EnrichmentRunSummary(company_id=company.id, provider=enricher.provider)
    result = enricher.enrich(company_name=company.canonical_name,
                             domain=company.primary_domain, website=company.website)
    summary.pages_fetched = result.pages_fetched
    summary.people_found = len(result.people)
    summary.contacts_found = len(result.contacts)
    summary.errors = list(result.errors)
    now = _now()
    domain = company.primary_domain

    # People.
    for p in result.people:
        existing, status = resolve_person(
            session, company_id=company.id,
            normalized_name=p["normalized_name"], normalized_role=p["normalized_role"])
        if status is PersonMatchStatus.EXACT_MATCH and existing is not None:
            existing.last_seen_at = now
            existing.last_verified_at = now
            self_refs = existing.source_references or []
            if p["source_url"] and p["source_url"] not in [r.get("source_url") for r in self_refs]:
                existing.source_references = self_refs + [{"source": p["contact_source"],
                                                          "source_url": p["source_url"], "observed_at": now.isoformat()}]
            summary.duplicates += 1
            continue
        conf = _person_confidences(p, company_domain=domain)
        fresh = compute_freshness(signal_type="COMPANY", observed_at=now, now=now)
        dm = DecisionMaker(
            company_id=company.id, company_name=company.canonical_name,
            full_name=p["full_name"], normalized_name=p["normalized_name"],
            job_title=p["job_title"], normalized_role=p["normalized_role"],
            role_category=p["role_category"], seniority=p.get("seniority"),
            profile_url=p.get("profile_url"),
            contact_source=p["contact_source"], source_type=p["source_type"],
            source_url=p["source_url"], collector_version="1.0.0",
            source_references=[{"source": p["contact_source"], "source_url": p["source_url"],
                               "observed_at": now.isoformat()}],
            freshness_score=fresh.score, data_provenance=provenance,
            match_status=status if existing is None else PersonMatchStatus.REVIEW_REQUIRED,
            first_seen_at=now, last_seen_at=now, last_verified_at=now, **conf,
        )
        dm.verification_status = _verification(conf["identity_confidence"], conf["role_confidence"],
                                               conf["company_confidence"], fresh.is_stale)
        session.add(dm)
        summary.people_accepted += 1

    # Business contacts (no person identity).
    for c in result.contacts:
        existing = session.scalar(select(DecisionMaker).where(
            DecisionMaker.company_id == company.id,
            DecisionMaker.business_email == c["business_email"]))
        if existing is not None:
            existing.last_seen_at = now
            summary.duplicates += 1
            continue
        fresh = compute_freshness(signal_type="COMPANY", observed_at=now, now=now)
        ev = _evidence_confidence(c["source_type"])
        dm = DecisionMaker(
            company_id=company.id, company_name=company.canonical_name,
            business_email=c["business_email"], contact_type=c["contact_type"],
            email_status=c["email_status"], role_category=RoleCategory.OTHER,
            contact_source=c["contact_source"], source_type=c["source_type"],
            source_url=c["source_url"], collector_version="1.0.0",
            source_references=[{"source": c["contact_source"], "source_url": c["source_url"],
                               "observed_at": now.isoformat()}],
            company_confidence=90, contact_confidence=80, evidence_confidence=ev,
            freshness_score=fresh.score, data_provenance=provenance,
            verification_status=VerificationStatus.PARTIALLY_VERIFIED,
            match_status=PersonMatchStatus.NO_MATCH,
            first_seen_at=now, last_seen_at=now, last_verified_at=now,
        )
        session.add(dm)
        summary.contacts_accepted += 1

    session.commit()
    logger.info("enrichment company_id=%s people=%s contacts=%s dupes=%s",
                company.id, summary.people_accepted, summary.contacts_accepted, summary.duplicates)
    return summary
