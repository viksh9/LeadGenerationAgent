"""EvidenceVerificationService — build evidence, verify, persist (idempotent).

Wires the verification engines to the existing Lead + evidence data. Re-verifying
a lead replaces its evidence records for the current verification_version (no
duplicates). Raw source data is never modified.
"""

from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from config.evidence import VERIFICATION_VERSION
from database.models import (
    ConflictSeverity,
    EvidenceConflict,
    EvidenceRecord,
    EvidenceType,
    Lead,
)
from processors.normalization.text import normalize_for_compare
from verification.conflicts import ConflictEvidence, detect_conflicts
from verification.lead_readiness import classify_readiness
from verification.signal_verification import EvidenceInput, VerificationResult, verify_evidence_set
from verification.source_reliability import compute_source_reliability, source_tier_for
from verification.url_validation import safe_domain

logger = logging.getLogger("verification")


def _parse_dt(value) -> Optional[datetime]:
    if value is None or isinstance(value, datetime):
        return value
    try:
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return dt.astimezone(timezone.utc).replace(tzinfo=None) if dt.tzinfo else dt
    except ValueError:
        return None


def _job_identity_hash(title: Optional[str], company: Optional[str]) -> str:
    key = f"{normalize_for_compare(title)}|{normalize_for_compare(company)}"
    return hashlib.sha256(key.encode("utf-8")).hexdigest()[:32]


def _lead_signal_type(lead: Lead) -> str:
    if lead.company_signals:
        return lead.company_signals[0]
    if lead.signal_type is not None:
        return lead.signal_type.value
    return "HIRING"


def _evidence_inputs(lead: Lead) -> list[EvidenceInput]:
    inputs: list[EvidenceInput] = []
    for e in (lead.evidence or []):
        title = e.get("job_title") or lead.signal_title
        source_id = e.get("source_id") or e.get("source") or (lead.source_name or "unknown")
        inputs.append(EvidenceInput(
            source_id=source_id,
            content_hash=_job_identity_hash(title, lead.normalized_company_name or lead.company_name),
            source_url=e.get("source_url"),
            published_at=_parse_dt(e.get("published_at")),
            normalized_company_name=lead.normalized_company_name,
            normalized_title=title,
        ))
    return inputs


@dataclass
class LeadVerification:
    result: VerificationResult
    evidence_count: int
    conflict_count: int


class EvidenceVerificationService:
    version = VERIFICATION_VERSION

    def __init__(self, session: Session) -> None:
        self.session = session

    def verify_lead(self, lead: Lead, *, now: Optional[datetime] = None, persist: bool = True) -> LeadVerification:
        now = now or datetime.now(timezone.utc).replace(tzinfo=None)
        inputs = _evidence_inputs(lead)
        signal_type = _lead_signal_type(lead)
        result = verify_evidence_set(inputs, signal_type=signal_type, now=now)

        has_signal = bool(lead.company_signals) or lead.it_job_count > 0 or lead.signal_type is not None
        readiness = classify_readiness(
            verification_status=result.verification_status,
            evidence_confidence=result.evidence_confidence,
            freshness_score=result.freshness_score,
            has_meaningful_signal=has_signal,
        )

        logger.info(
            "verify_lead lead_id=%s status=%s reliability=%s evidence_conf=%s freshness=%s "
            "independent=%s conflicts=%s readiness=%s",
            lead.id, result.verification_status.value, result.source_reliability, result.evidence_confidence,
            result.freshness_score, result.independent_support_count, result.contradictory_evidence_count,
            readiness.value,
        )

        if persist:
            self._persist(lead, inputs, result, now)
            lead.source_reliability = result.source_reliability
            lead.evidence_confidence = result.evidence_confidence
            lead.freshness_score = result.freshness_score
            lead.independent_support_count = result.independent_support_count
            lead.verification_status = result.verification_status
            lead.lead_readiness = readiness
            lead.verification_reason = " ".join(result.reasons)[:2000]
            lead.verification_version = self.version
            lead.verified_at = now
            self.session.commit()

        return LeadVerification(result, len(inputs), result.contradictory_evidence_count)

    def _persist(self, lead: Lead, inputs: list[EvidenceInput], result: VerificationResult, now: datetime) -> None:
        # Idempotent: replace this lead's evidence for the current version.
        self.session.execute(delete(EvidenceRecord).where(EvidenceRecord.lead_id == lead.id))
        self.session.execute(delete(EvidenceConflict).where(
            EvidenceConflict.subject_type == "LEAD", EvidenceConflict.subject_id == lead.id))

        # One evidence record per INDEPENDENCE GROUP (distinct underlying
        # evidence). Syndicated copies of the same job collapse into one row whose
        # source list names every source — so N URLs are not N confirmations.
        groups: dict[str, dict] = {}
        for e in inputs:
            gid = (e.content_hash or _job_identity_hash(e.normalized_title, lead.company_name))[:16]
            g = groups.setdefault(gid, {"rep": e, "sources": set(), "urls": set()})
            g["sources"].add(e.source_id)
            if e.source_url:
                g["urls"].add(e.source_url)
            # Keep the most authoritative source as representative.
            if source_tier_for(e.source_id).value < source_tier_for(g["rep"].source_id).value:
                g["rep"] = e

        for gid, g in list(groups.items())[:100]:
            rep = g["rep"]
            reliability = compute_source_reliability(rep.source_id, category=rep.source_category)
            self.session.add(EvidenceRecord(
                lead_id=lead.id, company_normalized_name=lead.normalized_company_name,
                evidence_type=EvidenceType.JOB,
                source_name=", ".join(sorted(g["sources"])), source_url=rep.source_url,
                source_domain=safe_domain(rep.source_url), source_tier=reliability.source_tier,
                published_at=rep.published_at, observed_at=now, last_verified_at=now,
                content_hash=rep.content_hash or gid, evidence_title=rep.normalized_title,
                evidence_summary=(f"{len(g['sources'])} source(s); {len(g['urls'])} URL(s)"),
                data_provenance=lead.data_provenance,
                source_reliability_score=reliability.reliability_score,
                authority_score=reliability.authority_score,
                freshness_score=result.freshness_score, corroboration_score=result.corroboration_score,
                evidence_confidence=result.evidence_confidence,
                independence_group_id=gid,
                verification_status=result.verification_status,
                verification_reason="; ".join(result.reasons[:3])[:1000],
                verification_version=self.version,
            ))

        # Persist detected conflicts (never silently discarded).
        findings = detect_conflicts([
            ConflictEvidence(i, e.source_id, source_tier_for(e.source_id, e.source_category),
                             e.normalized_company_name, e.normalized_title, e.city, e.status, e.project_status,
                             e.published_at)
            for i, e in enumerate(inputs)
        ])
        for f in findings:
            self.session.add(EvidenceConflict(
                subject_type="LEAD", subject_id=lead.id, conflict_type=f.conflict_type, severity=f.severity,
                description=f.description, data_provenance=lead.data_provenance,
            ))

    def get_lead_evidence(self, lead_id: int) -> list[EvidenceRecord]:
        return list(self.session.scalars(
            select(EvidenceRecord).where(EvidenceRecord.lead_id == lead_id).order_by(EvidenceRecord.source_tier)
        ))

    def get_lead_conflicts(self, lead_id: int) -> list[EvidenceConflict]:
        return list(self.session.scalars(
            select(EvidenceConflict).where(
                EvidenceConflict.subject_type == "LEAD", EvidenceConflict.subject_id == lead_id)
        ))
