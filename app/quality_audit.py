"""Data-quality scorecard (Prompt 41 §11-§19, §53).

Computes ACTUAL completeness/quality percentages from the database. Never
fabricates a percentage; a section with zero records reports counts of 0 and
``INSUFFICIENT_DATA`` for ratios rather than a made-up figure.
"""

from __future__ import annotations

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from database.models import (
    Company,
    DataProvenance,
    DecisionMaker,
    EvidenceConflict,
    EvidenceRecord,
    JobRecord,
    JobSourceReference,
    Lead,
    LeadReadiness,
    OpportunityCandidate,
    BusinessSignal,
    VerificationStatus,
)

INSUFFICIENT = "INSUFFICIENT_DATA"


def _count(session, model, *where) -> int:
    stmt = select(func.count()).select_from(model)
    for w in where:
        stmt = stmt.where(w)
    return int(session.execute(stmt).scalar() or 0)


def _pct(n: int, total: int):
    if total <= 0:
        return INSUFFICIENT
    return round(100.0 * n / total, 1)


def quality_report(session: Session) -> dict:
    # --- Jobs (§12) ---
    jobs = _count(session, JobRecord)
    linked = select(JobSourceReference.job_record_id).distinct()
    jobs_q = {
        "total": jobs,
        "pct_with_company": _pct(_count(session, JobRecord,
            JobRecord.normalized_company_name.is_not(None),
            func.trim(JobRecord.normalized_company_name) != ""), jobs),
        "pct_with_source_reference": _pct(_count(session, JobRecord, JobRecord.id.in_(linked)), jobs),
        "pct_with_technology": _pct(_count(session, JobRecord, func.json_array_length(JobRecord.technologies) > 0), jobs)
            if jobs else INSUFFICIENT,
        "pct_with_published_at": _pct(_count(session, JobRecord, JobRecord.published_at.is_not(None)), jobs),
        "pct_with_content_hash": _pct(_count(session, JobRecord,
            JobRecord.content_hash.is_not(None), func.trim(JobRecord.content_hash) != ""), jobs),
    }
    # Duplicate canonical jobs (same content hash more than once).
    dup_rows = session.execute(
        select(JobRecord.content_hash, func.count(JobRecord.id))
        .group_by(JobRecord.content_hash).having(func.count(JobRecord.id) > 1)
    ).all()
    jobs_q["duplicate_canonical_jobs"] = sum(int(n) - 1 for _, n in dup_rows)

    # --- Companies (§13) ---
    companies = _count(session, Company)
    dup_co = session.execute(
        select(Company.normalized_name, func.count(Company.id))
        .group_by(Company.normalized_name).having(func.count(Company.id) > 1)
    ).all()
    companies_q = {
        "total": companies,
        "pct_with_domain": _pct(_count(session, Company,
            Company.primary_domain.is_not(None), func.trim(Company.primary_domain) != ""), companies),
        "pct_verified": _pct(_count(session, Company,
            Company.verification_status.in_([VerificationStatus.VERIFIED,
                                             VerificationStatus.PARTIALLY_VERIFIED])), companies),
        "review_required": _count(session, Company,
            Company.verification_status == VerificationStatus.UNVERIFIED),
        "possible_duplicate_name_groups": len(dup_co),
    }

    # --- Evidence (§15) ---
    evidence = _count(session, EvidenceRecord)
    evidence_q = {
        "total": evidence,
        "pct_with_source_name": _pct(_count(session, EvidenceRecord,
            EvidenceRecord.source_name.is_not(None), func.trim(EvidenceRecord.source_name) != ""), evidence),
        "pct_with_source_url": _pct(_count(session, EvidenceRecord,
            EvidenceRecord.source_url.is_not(None), func.trim(EvidenceRecord.source_url) != ""), evidence),
        "pct_verified": _pct(_count(session, EvidenceRecord,
            EvidenceRecord.verification_status.in_([VerificationStatus.VERIFIED,
                                                    VerificationStatus.PARTIALLY_VERIFIED])), evidence),
        "pct_stale": _pct(_count(session, EvidenceRecord,
            EvidenceRecord.verification_status == VerificationStatus.STALE), evidence),
        "unresolved_conflicts": _count(session, EvidenceConflict,
            EvidenceConflict.resolution_status == "UNRESOLVED"),
    }

    # --- Signals (§16) ---
    signals = _count(session, BusinessSignal)
    signals_q = {
        "total": signals,
        "pct_with_company": _pct(_count(session, BusinessSignal,
            or_(BusinessSignal.company_id.is_not(None),
                func.trim(BusinessSignal.normalized_company_name) != "")), signals),
        "pct_with_source": _pct(_count(session, BusinessSignal,
            BusinessSignal.source_id.is_not(None), func.trim(BusinessSignal.source_id) != ""), signals),
    }

    # --- Opportunities (§17) ---
    opps = _count(session, OpportunityCandidate)
    opps_q = {
        "total": opps,
        "pct_with_basis": _pct(_count(session, OpportunityCandidate,
            or_(OpportunityCandidate.total_business_signals > 0,
                OpportunityCandidate.it_job_count > 0)), opps),
    }

    # --- Leads (§18) ---
    leads = _count(session, Lead, Lead.data_provenance == DataProvenance.REAL)
    with_ev = select(EvidenceRecord.lead_id).where(EvidenceRecord.lead_id.is_not(None)).distinct()
    leads_q = {
        "total_real": leads,
        "pct_with_evidence": _pct(_count(session, Lead,
            Lead.data_provenance == DataProvenance.REAL, Lead.id.in_(with_ev)), leads),
        "pct_ready": _pct(_count(session, Lead,
            Lead.data_provenance == DataProvenance.REAL,
            Lead.lead_readiness == LeadReadiness.READY), leads),
    }

    # --- Contacts (§19) ---
    contacts = _count(session, DecisionMaker)
    contacts_q = {
        "total": contacts,
        "pct_with_source": _pct(_count(session, DecisionMaker,
            or_(DecisionMaker.source_url.is_not(None), DecisionMaker.source_type.is_not(None))), contacts),
        "pct_verified": _pct(_count(session, DecisionMaker,
            DecisionMaker.verification_status.in_([VerificationStatus.VERIFIED,
                                                   VerificationStatus.PARTIALLY_VERIFIED])), contacts),
    }

    return {
        "jobs": jobs_q, "companies": companies_q, "evidence": evidence_q,
        "signals": signals_q, "opportunities": opps_q, "leads": leads_q, "contacts": contacts_q,
    }
