"""Provenance audit (Prompt 41 §3, §21).

Verifies that every production business record is traceable to a real source and
backed by evidence. Reports ACTUAL counts of records failing each provenance
rule; never mutates data. Used by ``python -m app.audit provenance``.
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from database.models import (
    AIIntelligenceResult,
    BusinessSignal,
    Company,
    DataProvenance,
    DecisionMaker,
    EvidenceRecord,
    JobRecord,
    JobSourceReference,
    Lead,
    OpportunityCandidate,
    RawSourceRecord,
    TenderRecord,
)


@dataclass
class ProvenanceCheck:
    name: str
    failures: int
    detail: str

    @property
    def ok(self) -> bool:
        return self.failures == 0


def _count(session: Session, model, *where) -> int:
    stmt = select(func.count()).select_from(model)
    for w in where:
        stmt = stmt.where(w)
    return int(session.execute(stmt).scalar() or 0)


def provenance_report(session: Session) -> dict:
    checks: list[ProvenanceCheck] = []

    # Raw source records: identity + collection metadata.
    checks.append(ProvenanceCheck(
        "raw_missing_source_id", _count(session, RawSourceRecord,
            or_(RawSourceRecord.source_id.is_(None), func.trim(RawSourceRecord.source_id) == "")),
        "raw records without a source_id"))
    checks.append(ProvenanceCheck(
        "raw_missing_content_hash", _count(session, RawSourceRecord,
            or_(RawSourceRecord.content_hash.is_(None), func.trim(RawSourceRecord.content_hash) == "")),
        "raw records without a content hash"))
    checks.append(ProvenanceCheck(
        "raw_missing_external_id_and_url", _count(session, RawSourceRecord,
            RawSourceRecord.external_id.is_(None), RawSourceRecord.source_url.is_(None)),
        "raw records with neither a source record id nor a source URL"))
    checks.append(ProvenanceCheck(
        "raw_missing_collected_at", _count(session, RawSourceRecord, RawSourceRecord.collected_at.is_(None)),
        "raw records without an observed/collected timestamp"))

    # Canonical jobs: content hash + at least one source reference.
    linked_job_ids = select(JobSourceReference.job_record_id).distinct()
    checks.append(ProvenanceCheck(
        "jobs_without_source_reference", _count(session, JobRecord, JobRecord.id.not_in(linked_job_ids)),
        "canonical jobs with no source reference"))
    checks.append(ProvenanceCheck(
        "jobs_missing_provenance", _count(session, JobRecord, JobRecord.data_provenance.is_(None)),
        "canonical jobs without a provenance flag"))

    # Companies: provenance present.
    checks.append(ProvenanceCheck(
        "companies_missing_provenance", _count(session, Company, Company.data_provenance.is_(None)),
        "companies without a provenance flag"))

    # Business signals: source identity + not orphaned.
    checks.append(ProvenanceCheck(
        "signals_missing_source", _count(session, BusinessSignal,
            or_(BusinessSignal.source_id.is_(None), func.trim(BusinessSignal.source_id) == "")),
        "signals without a source id"))
    checks.append(ProvenanceCheck(
        "signals_orphaned", _count(session, BusinessSignal,
            BusinessSignal.company_id.is_(None), BusinessSignal.raw_record_id.is_(None),
            or_(BusinessSignal.normalized_company_name.is_(None),
                func.trim(BusinessSignal.normalized_company_name) == "")),
        "signals with no company, raw record, or company name"))

    # Opportunities: not orphaned (must have a basis — signals or jobs or a company).
    checks.append(ProvenanceCheck(
        "opportunities_without_basis", _count(session, OpportunityCandidate,
            OpportunityCandidate.total_business_signals == 0, OpportunityCandidate.it_job_count == 0),
        "opportunity candidates with no signals and no jobs"))

    # Leads: REAL leads must have evidence + a source.
    leads_with_evidence = select(EvidenceRecord.lead_id).where(
        EvidenceRecord.lead_id.is_not(None)).distinct()
    checks.append(ProvenanceCheck(
        "leads_without_evidence", _count(session, Lead,
            Lead.data_provenance == DataProvenance.REAL, Lead.id.not_in(leads_with_evidence)),
        "REAL leads with no evidence record"))
    checks.append(ProvenanceCheck(
        "leads_without_source", _count(session, Lead,
            Lead.data_provenance == DataProvenance.REAL,
            or_(Lead.source_url.is_(None), func.trim(Lead.source_url) == ""),
            or_(Lead.source_name.is_(None), func.trim(Lead.source_name) == "")),
        "REAL leads with neither a source URL nor a source name"))

    # Evidence: must be traceable to a source (URL, name, OR domain — any one is
    # provenance). Missing ALL three is a real failure; missing only the optional
    # URL is a data-quality signal reported by the quality scorecard, not here.
    checks.append(ProvenanceCheck(
        "evidence_missing_all_source", _count(session, EvidenceRecord,
            or_(EvidenceRecord.source_url.is_(None), func.trim(EvidenceRecord.source_url) == ""),
            or_(EvidenceRecord.source_name.is_(None), func.trim(EvidenceRecord.source_name) == ""),
            or_(EvidenceRecord.source_domain.is_(None), func.trim(EvidenceRecord.source_domain) == "")),
        "evidence records with no source URL, name, or domain"))
    checks.append(ProvenanceCheck(
        "evidence_missing_observed_at", _count(session, EvidenceRecord,
            EvidenceRecord.observed_at.is_(None), EvidenceRecord.published_at.is_(None)),
        "evidence records without an observed/published timestamp"))

    # Evidence broken links: lead_id set but the lead no longer exists.
    lead_ids = select(Lead.id)
    checks.append(ProvenanceCheck(
        "evidence_broken_lead_link", _count(session, EvidenceRecord,
            EvidenceRecord.lead_id.is_not(None), EvidenceRecord.lead_id.not_in(lead_ids)),
        "evidence records pointing at a missing lead"))

    # Contacts: must have a source (url or source_type).
    checks.append(ProvenanceCheck(
        "contacts_without_source", _count(session, DecisionMaker,
            DecisionMaker.source_url.is_(None), DecisionMaker.source_type.is_(None)),
        "contacts with neither a source URL nor a source type"))

    # Tenders: source identity.
    checks.append(ProvenanceCheck(
        "tenders_missing_source", _count(session, TenderRecord,
            or_(TenderRecord.source_id.is_(None), func.trim(TenderRecord.source_id) == "")),
        "tenders without a source id"))

    # AI claims: every persisted FACT claim must reference evidence ids.
    checks.append(ProvenanceCheck(
        "ai_facts_without_evidence", _ai_facts_without_evidence(session),
        "AI FACT claims with no evidence_ids reference"))

    total = sum(c.failures for c in checks)
    return {
        "total_failures": total,
        "ok": total == 0,
        "checks": [{"name": c.name, "failures": c.failures, "detail": c.detail, "ok": c.ok}
                   for c in checks],
    }


def _ai_facts_without_evidence(session: Session) -> int:
    """Count persisted AI results whose FACT claims cite no evidence. FACT claims
    are stored in verified_facts JSON as dicts with claim_type FACT + evidence_ids."""
    rows = session.execute(select(AIIntelligenceResult)).scalars().all()
    bad = 0
    for r in rows:
        for claim in (r.verified_facts or []):
            if not isinstance(claim, dict):
                continue
            ctype = str(claim.get("claim_type", "")).upper()
            if ctype == "FACT" and not claim.get("evidence_ids"):
                bad += 1
                break   # count the result once
    return bad
