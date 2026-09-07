"""Company services: entity resolution, company upsert from canonical jobs, and
the intelligence profile. Business logic lives here (out of route handlers)."""

from __future__ import annotations

import logging
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import delete, select, update
from sqlalchemy.orm import Session

from company import repository as repo
from company.classification import classify_company
from company.intelligence import build_company_intelligence
from company.normalization import normalize_domain, normalize_name
from company.resolver import CompanyEntityResolver, CompanyResolutionResult, ObservedCompany
from config.company import COMPANY_RESOLUTION_VERSION
from config.locations_in import INDIAN_CITY_ALIASES
from database.models import (
    Company,
    CompanyMatchStatus,
    CompanyResolutionCandidate,
    CompanyResolutionDecision,
    DataProvenance,
    JobRecord,
    Lead,
)

logger = logging.getLogger("company")

_INDIAN_CITIES = set(INDIAN_CITY_ALIASES.keys())


@dataclass
class CompanyRunSummary:
    provenance: str
    companies_created: int = 0
    companies_updated: int = 0
    linked_leads: int = 0
    review_candidates: int = 0


def _identity_confidence(name: Optional[str], domain: Optional[str], city: Optional[str]) -> int:
    conf = 0
    conf += 40 if name and len(name.strip()) >= 3 else 0
    conf += 40 if domain else 0
    conf += 10 if city else 0
    return min(100, conf)


class CompanyResolutionService:
    version = COMPANY_RESOLUTION_VERSION

    def __init__(self, session: Session, resolver: Optional[CompanyEntityResolver] = None) -> None:
        self.session = session
        self.resolver = resolver or CompanyEntityResolver()

    def resolve(self, obs: ObservedCompany, *, provenance: DataProvenance) -> CompanyResolutionResult:
        norm = normalize_name(obs.name).normalized_name
        domain = normalize_domain(obs.domain or obs.website)
        candidates = repo.candidate_block(self.session, normalized_name=norm, domain=domain, provenance=provenance)
        return self.resolver.resolve(obs, candidates)

    def resolve_and_upsert(self, obs: ObservedCompany, *, provenance: DataProvenance,
                           now: Optional[datetime] = None) -> tuple[Company, CompanyResolutionResult]:
        now = now or datetime.now(timezone.utc).replace(tzinfo=None)
        result = self.resolve(obs, provenance=provenance)
        domain = normalize_domain(obs.domain or obs.website)

        if result.recommended_action == "LINK" and result.matched_company_id is not None:
            company = repo.get_company(self.session, result.matched_company_id)
            company.last_seen_at = now
            created = False
        else:
            company = repo.create_company(
                self.session,
                canonical_name=obs.name or (domain or "Unknown"),
                normalized_name=normalize_name(obs.name).normalized_name or (domain or "unknown"),
                primary_domain=domain, website=obs.website, legal_name=obs.legal_name,
                headquarters_city=None,   # never assume HQ from a job location
                identity_confidence=_identity_confidence(obs.name, domain, obs.city),
                data_provenance=provenance, first_seen_at=now, last_seen_at=now,
            )
            created = True
            repo.add_event(self.session, company.id, "company_created",
                           f"Created from {obs.source_id or 'source'} ({result.match_status.value}).",
                           provenance=provenance)
            # Uncertain match -> keep separate but flag for human review (never silent merge).
            if result.recommended_action == "REVIEW" and result.candidate_companies:
                repo.add_resolution_candidate(
                    self.session, observed_name=obs.name, observed_domain=domain, observed_location=obs.city,
                    candidate_company_id=result.candidate_companies[0], match_status=result.match_status,
                    confidence=result.confidence, matching_factors=result.matching_factors,
                    conflicting_factors=result.conflicting_factors,
                    resolution_explanation=f"[new_company_id={company.id}] {result.resolution_explanation}",
                    data_provenance=provenance,
                )

        repo.add_source_reference(
            self.session, company, source_name=obs.source_id, source_url=obs.source_url,
            observed_name=obs.name, observed_domain=domain, observed_location=obs.city,
            confidence=result.confidence, first_seen_at=now, last_seen_at=now,
        )
        self.session.flush()
        return company, result

    def upsert_companies_from_jobs(self, *, provenance: DataProvenance = DataProvenance.REAL,
                                   now: Optional[datetime] = None) -> CompanyRunSummary:
        now = now or datetime.now(timezone.utc).replace(tzinfo=None)
        summary = CompanyRunSummary(provenance=provenance.value)
        jobs = list(self.session.scalars(
            select(JobRecord).where(JobRecord.data_provenance == provenance)))
        by_company: dict[str, list[JobRecord]] = {}
        for j in jobs:
            if j.normalized_company_name:
                by_company.setdefault(j.normalized_company_name, []).append(j)

        for norm, group in by_company.items():
            rep = max(group, key=lambda j: (bool(j.company_domain), len(j.company_name or "")))
            obs = ObservedCompany(name=rep.company_name, domain=rep.company_domain,
                                  city=rep.city, source_id=rep.primary_source, source_url=None)
            company, result = self.resolve_and_upsert(obs, provenance=provenance, now=now)
            if result.recommended_action == "LINK":
                summary.companies_updated += 1
            else:
                summary.companies_created += 1
            if result.recommended_action == "REVIEW":
                summary.review_candidates += 1

            # Aggregate evidence-based fields.
            cities = [c for c in {j.city for j in group if j.city}]
            india_locs = [c for c in cities if c in _INDIAN_CITIES]
            techs = Counter(t for j in group for t in (j.technologies or []))
            industries = Counter(j.job_category for j in group if j.job_category)
            industry = industries.most_common(1)[0][0] if industries else company.industry
            cls = classify_company(industry_text=industry, technologies=list(techs), job_count=len(group))

            company.india_locations = india_locs
            company.india_presence = bool(india_locs) or company.india_presence
            company.industry = industry
            company.company_type = cls.company_type
            company.company_types = cls.company_types
            company.last_seen_at = now
            repo.add_event(self.session, company.id, "hiring_updated",
                           f"{len(group)} canonical openings; top tech {', '.join(t for t, _ in techs.most_common(3))}.",
                           provenance=provenance)

            # Link the company-level Lead(s) + propagate verification confidence.
            leads = list(self.session.scalars(
                select(Lead).where(Lead.normalized_company_name == norm, Lead.data_provenance == provenance)))
            for lead in leads:
                lead.company_id = company.id
                summary.linked_leads += 1
            if leads:
                best = max(leads, key=lambda l: l.evidence_confidence)
                company.evidence_confidence = best.evidence_confidence
                company.verification_status = best.verification_status

        self.session.commit()
        logger.info("company_upsert provenance=%s created=%s updated=%s linked_leads=%s review=%s",
                    provenance.value, summary.companies_created, summary.companies_updated,
                    summary.linked_leads, summary.review_candidates)
        return summary

    def resolve_review(self, candidate_id: int, decision: CompanyResolutionDecision) -> bool:
        cand = self.session.get(CompanyResolutionCandidate, candidate_id)
        if cand is None:
            return False
        cand.status = decision
        if decision is CompanyResolutionDecision.MERGE and cand.candidate_company_id:
            # Relink the tentative company's leads to the confirmed company, then remove it.
            import re
            m = re.search(r"new_company_id=(\d+)", cand.resolution_explanation or "")
            if m:
                new_id = int(m.group(1))
                self.session.execute(update(Lead).where(Lead.company_id == new_id)
                                     .values(company_id=cand.candidate_company_id))
                self.session.execute(delete(Company).where(Company.id == new_id))
        self.session.commit()
        return True


class CompanyIntelligenceService:
    def __init__(self, session: Session) -> None:
        self.session = session

    def profile(self, company_id: int, *, now: Optional[datetime] = None) -> Optional[dict]:
        company = repo.get_company(self.session, company_id)
        if company is None:
            return None
        return build_company_intelligence(self.session, company, now=now)
