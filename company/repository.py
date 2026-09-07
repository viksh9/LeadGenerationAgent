"""Company persistence: CRUD, candidate blocking, search, references,
relationships, events, and the entity-resolution review queue.

Indexes on normalized_name / primary_domain / industry / verification_status make
blocking + search cheap (no O(N^2) scans).
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from company.normalization import normalize_name
from company.resolver import CompanyCandidate
from database.models import (
    BusinessSignal,
    Company,
    CompanyEvent,
    CompanyRelationship,
    CompanyResolutionCandidate,
    CompanyResolutionDecision,
    CompanySourceReference,
    DataProvenance,
    EvidenceRecord,
    JobRecord,
    Lead,
)


def get_company(session: Session, company_id: int) -> Optional[Company]:
    return session.get(Company, company_id)


def find_by_domain(session: Session, domain: str, provenance: DataProvenance) -> Optional[Company]:
    if not domain:
        return None
    return session.scalars(
        select(Company).where(Company.primary_domain == domain, Company.data_provenance == provenance)
    ).first()


def candidate_block(
    session: Session, *, normalized_name: str, domain: Optional[str], provenance: DataProvenance, limit: int = 25
) -> list[CompanyCandidate]:
    """Cheap candidate selection: exact domain OR exact normalized name OR shared
    leading token — never a full scan."""
    tokens = normalize_name(normalized_name).tokens
    conditions = [Company.normalized_name == normalized_name]
    if domain:
        conditions.append(Company.primary_domain == domain)
    if tokens:
        conditions.append(Company.normalized_name.like(f"{tokens[0]}%"))
    stmt = select(Company).where(Company.data_provenance == provenance, or_(*conditions)).limit(limit)
    out = []
    for co in session.scalars(stmt):
        out.append(CompanyCandidate(
            id=co.id, normalized_name=co.normalized_name, primary_domain=co.primary_domain,
            alternate_domains=list(co.alternate_domains or []), legal_name=co.legal_name,
            headquarters_city=co.headquarters_city, tokens=normalize_name(co.canonical_name).tokens,
        ))
    return out


def create_company(session: Session, **fields: Any) -> Company:
    company = Company(**fields)
    session.add(company)
    session.flush()
    return company


def add_source_reference(session: Session, company: Company, **fields: Any) -> CompanySourceReference:
    # Update an existing reference for the same (source, url) rather than duplicating.
    for ref in company.source_references:
        if ref.source_name == fields.get("source_name") and ref.source_url == fields.get("source_url"):
            ref.last_seen_at = fields.get("last_seen_at", ref.last_seen_at)
            ref.observed_name = fields.get("observed_name", ref.observed_name)
            return ref
    ref = CompanySourceReference(company_id=company.id, **fields)
    session.add(ref)
    return ref


def add_event(session: Session, company_id: int, event_type: str, description: str,
              *, old_value: str | None = None, new_value: str | None = None,
              provenance: DataProvenance = DataProvenance.REAL) -> CompanyEvent:
    ev = CompanyEvent(company_id=company_id, event_type=event_type, description=description,
                      old_value=old_value, new_value=new_value, data_provenance=provenance)
    session.add(ev)
    return ev


def add_relationship(session: Session, from_id: int, to_id: int, rel_type, *, evidence: str,
                     confidence: int, source: str | None = None,
                     provenance: DataProvenance = DataProvenance.REAL) -> CompanyRelationship:
    rel = CompanyRelationship(from_company_id=from_id, to_company_id=to_id, relationship_type=rel_type,
                              evidence=evidence, confidence=confidence, source=source, data_provenance=provenance)
    session.add(rel)
    return rel


def add_resolution_candidate(session: Session, **fields: Any) -> CompanyResolutionCandidate:
    cand = CompanyResolutionCandidate(**fields)
    session.add(cand)
    return cand


# --- Company-scoped intelligence queries ----------------------------------- #
def company_jobs(session: Session, normalized_name: str, provenance: DataProvenance) -> list[JobRecord]:
    return list(session.scalars(
        select(JobRecord).where(JobRecord.normalized_company_name == normalized_name,
                                JobRecord.data_provenance == provenance)))


def company_signals(session: Session, normalized_name: str, provenance: DataProvenance) -> list[BusinessSignal]:
    return list(session.scalars(
        select(BusinessSignal).where(BusinessSignal.normalized_company_name == normalized_name,
                                     BusinessSignal.data_provenance == provenance)))


def company_leads(session: Session, company_id: int) -> list[Lead]:
    return list(session.scalars(select(Lead).where(Lead.company_id == company_id)))


def company_evidence(session: Session, normalized_name: str) -> list[EvidenceRecord]:
    return list(session.scalars(
        select(EvidenceRecord).where(EvidenceRecord.company_normalized_name == normalized_name)))


def company_history(session: Session, company_id: int) -> list[CompanyEvent]:
    return list(session.scalars(
        select(CompanyEvent).where(CompanyEvent.company_id == company_id).order_by(CompanyEvent.created_at.desc())))


# --- Search / review -------------------------------------------------------- #
_SORT = {"canonical_name": Company.canonical_name, "updated_at": Company.updated_at,
         "identity_confidence": Company.identity_confidence, "evidence_confidence": Company.evidence_confidence}


def search_companies(
    session: Session, *, search: str | None = None, industry: str | None = None,
    city: str | None = None, verification_status: Any = None, company_type: Any = None,
    provenance: Any = None, sort_by: str = "updated_at", sort_order: str = "desc",
    page: int = 1, page_size: int = 20,
) -> tuple[list[Company], int]:
    conditions = []
    if search:
        like = f"%{search.lower()}%"
        conditions.append(or_(func.lower(Company.canonical_name).like(like),
                              func.lower(func.coalesce(Company.primary_domain, "")).like(like),
                              func.lower(Company.normalized_name).like(like)))
    if industry:
        conditions.append(func.lower(func.coalesce(Company.industry, "")).like(f"%{industry.lower()}%"))
    if city:
        conditions.append(func.lower(func.coalesce(Company.headquarters_city, "")).like(f"%{city.lower()}%"))
    if verification_status is not None:
        conditions.append(Company.verification_status == verification_status)
    if company_type is not None:
        conditions.append(Company.company_type == company_type)
    if provenance is not None:
        conditions.append(Company.data_provenance == provenance)

    base = select(Company)
    for c in conditions:
        base = base.where(c)
    total = session.scalar(select(func.count()).select_from(base.subquery())) or 0
    col = _SORT.get(sort_by, Company.updated_at)
    order = col.asc() if sort_order == "asc" else col.desc()
    stmt = base.order_by(order, Company.id.desc()).offset((page - 1) * page_size).limit(page_size)
    return list(session.scalars(stmt)), int(total)


def list_review_candidates(session: Session, *, provenance: Any = None, limit: int = 50) -> list[CompanyResolutionCandidate]:
    stmt = select(CompanyResolutionCandidate).where(
        CompanyResolutionCandidate.status == CompanyResolutionDecision.PENDING)
    if provenance is not None:
        stmt = stmt.where(CompanyResolutionCandidate.data_provenance == provenance)
    return list(session.scalars(stmt.order_by(CompanyResolutionCandidate.confidence.desc()).limit(limit)))
