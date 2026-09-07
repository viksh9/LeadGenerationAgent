"""AI input context — assembled ONLY from real, source-backed database records.

The context is the strict fact base the AI reasoning layer may use. It is sanitized
(HTML/scripts stripped, lengths capped), minimized (no secrets, no raw payloads, no
unnecessary personal data), and every factual item carries an evidence/source
reference so downstream reasoning (deterministic or LLM) can be grounded and
validated. Nothing outside this context may be treated as fact.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from company import repository as company_repo
from collectors.raw_record import normalize_company_name
from database.models import Company, DecisionMaker, Lead, TenderRecord, VerificationStatus

_TAG_RE = re.compile(r"<[^>]+>")
_MAX_TEXT = 600


def sanitize_text(value: Optional[str], *, max_len: int = _MAX_TEXT) -> Optional[str]:
    """Strip tags/scripts, collapse whitespace, cap length. Source text is DATA."""
    if not value or not isinstance(value, str):
        return None
    cleaned = _TAG_RE.sub(" ", value)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    if len(cleaned) > max_len:
        cleaned = cleaned[:max_len].rstrip() + "…"
    return cleaned or None


@dataclass
class EvidenceItem:
    evidence_id: Optional[int]
    evidence_type: Optional[str]
    source: Optional[str]
    source_url: Optional[str]
    confidence: Optional[int]
    observed_at: Optional[str]


@dataclass
class LeadIntelligenceContext:
    subject_type: str
    subject_id: int
    company_id: Optional[int]
    lead_id: Optional[int]
    company_name: Optional[str]
    # Scoring (deterministic, authoritative — AI must keep these separate).
    lead_score: float
    lead_priority: Optional[str]
    evidence_confidence: int
    source_reliability: int
    verification_status: Optional[str]
    freshness_score: int
    # Real observed facts.
    canonical_job_count: int
    recent_job_count: int
    technologies: list[str]
    hiring_roles: list[str]
    company_signals: list[str]
    source_count: int
    last_signal_date: Optional[str]
    opportunity_summary: Optional[str]
    tenders: list[dict] = field(default_factory=list)
    evidence: list[dict] = field(default_factory=list)
    conflicts: list[dict] = field(default_factory=list)
    decision_makers: list[dict] = field(default_factory=list)
    provenance: str = "REAL"
    generated_at: str = ""

    def as_dict(self) -> dict:
        return asdict(self)

    def context_hash(self) -> str:
        """Stable hash of the factual context (excludes generated_at) for caching."""
        payload = {k: v for k, v in self.as_dict().items() if k != "generated_at"}
        return hashlib.sha256(json.dumps(payload, sort_keys=True, default=str).encode()).hexdigest()

    @property
    def is_stale(self) -> bool:
        return self.freshness_score > 0 and self.freshness_score <= 30

    @property
    def has_conflict(self) -> bool:
        return bool(self.conflicts)


def _iso(dt: Optional[datetime]) -> Optional[str]:
    return dt.isoformat() if isinstance(dt, datetime) else None


def _now_iso() -> str:
    return datetime.now(timezone.utc).replace(tzinfo=None).isoformat()


def _company_for_lead(session: Session, lead: Lead) -> Optional[Company]:
    norm = lead.normalized_company_name or normalize_company_name(lead.company_name or "")
    if not norm:
        return None
    return session.scalar(select(Company).where(Company.normalized_name == norm))


def _evidence_and_conflicts(session: Session, lead_id: int) -> tuple[list[dict], list[dict]]:
    try:
        from verification.service import EvidenceVerificationService

        svc = EvidenceVerificationService(session)
        records = svc.get_lead_evidence(lead_id)
        conflicts = svc.get_lead_conflicts(lead_id)
    except Exception:  # noqa: BLE001 - evidence is best-effort context, never fabricated
        return [], []
    ev = [EvidenceItem(
        evidence_id=getattr(r, "id", None),
        evidence_type=getattr(getattr(r, "evidence_type", None), "value", getattr(r, "evidence_type", None)),
        source=getattr(r, "source_name", None) or getattr(r, "source_id", None),
        source_url=getattr(r, "source_url", None),
        confidence=getattr(r, "evidence_confidence", None) or getattr(r, "confidence", None),
        observed_at=_iso(getattr(r, "observed_at", None)),
    ).__dict__ for r in records]
    conf = [{
        "conflict_type": getattr(getattr(c, "conflict_type", None), "value", getattr(c, "conflict_type", None)),
        "severity": getattr(getattr(c, "severity", None), "value", getattr(c, "severity", None)),
        "description": sanitize_text(getattr(c, "description", None)),
    } for c in conflicts]
    return ev, conf


def _tenders_for_company(session: Session, norm_name: str) -> list[dict]:
    out = []
    for t in session.scalars(select(TenderRecord)).all():
        if normalize_company_name(t.organization_name or "") != norm_name:
            continue
        out.append({
            "tender_id": t.id, "title": sanitize_text(t.title, max_len=200),
            "status": t.tender_status.value, "technologies": list(t.technologies or []),
            "estimated_value": t.estimated_value, "currency": t.currency,
            "closing_date": _iso(t.closing_date), "source_url": t.source_url,
        })
    return out


def _decision_makers(session: Session, company_id: int) -> list[dict]:
    rows = session.scalars(select(DecisionMaker).where(DecisionMaker.company_id == company_id)).all()
    return [{
        "role": dm.normalized_role or dm.job_title, "role_category": dm.role_category.value,
        "has_person": bool(dm.full_name), "verification_status": dm.verification_status.value,
        "source_url": dm.source_url,
    } for dm in rows]


def build_company_context(session: Session, company: Company) -> LeadIntelligenceContext:
    """Assemble a grounded context for a company from its real aggregated records."""
    from database.models import DataProvenance

    norm = company.normalized_name
    jobs = company_repo.company_jobs(session, norm, DataProvenance.REAL)
    signals = company_repo.company_signals(session, norm, DataProvenance.REAL)
    leads = company_repo.company_leads(session, company.id)
    techs: dict[str, int] = {}
    for j in jobs:
        for t in (j.technologies or []):
            techs[t] = techs.get(t, 0) + 1
    top_techs = [t for t, _ in sorted(techs.items(), key=lambda kv: -kv[1])]
    best = max(leads, key=lambda l: (l.lead_score or 0), default=None)
    evidence_ids = []  # company-level evidence lives per-lead; keep grounded via jobs/signals

    return LeadIntelligenceContext(
        subject_type="COMPANY", subject_id=company.id,
        company_id=company.id, lead_id=best.id if best else None,
        company_name=company.canonical_name,
        lead_score=float(best.lead_score or 0) if best else 0.0,
        lead_priority=getattr(best.lead_priority, "value", None) if best else None,
        evidence_confidence=int(company.evidence_confidence or 0),
        source_reliability=int(getattr(best, "source_reliability", 0) or 0) if best else 0,
        verification_status=getattr(company.verification_status, "value", None),
        freshness_score=int(getattr(best, "freshness_score", 0) or 0) if best else 0,
        canonical_job_count=len(jobs),
        recent_job_count=sum(1 for j in jobs if getattr(j, "recency_bucket", None)),
        technologies=top_techs,
        hiring_roles=list(getattr(best, "hiring_roles", None) or []) if best else [],
        company_signals=sorted({s.signal_type.value for s in signals}),
        source_count=int(getattr(best, "source_count", 0) or 0) if best else len(jobs),
        last_signal_date=_iso(max((s.published_at for s in signals if s.published_at), default=None)),
        opportunity_summary=sanitize_text(getattr(best, "opportunity_summary", None)) if best else None,
        tenders=_tenders_for_company(session, norm),
        evidence=[], conflicts=[],
        decision_makers=_decision_makers(session, company.id),
        provenance=getattr(company.data_provenance, "value", "REAL"),
        generated_at=_now_iso(),
    )


def build_lead_context(session: Session, lead: Lead) -> LeadIntelligenceContext:
    """Assemble a grounded, sanitized, minimized context for one real lead."""
    company = _company_for_lead(session, lead)
    norm = lead.normalized_company_name or normalize_company_name(lead.company_name or "") or ""
    evidence, conflicts = _evidence_and_conflicts(session, lead.id)
    tenders = _tenders_for_company(session, norm) if norm else []
    dms = _decision_makers(session, company.id) if company else []
    source_ids = sorted({e.get("source") for e in evidence if e.get("source")})

    return LeadIntelligenceContext(
        subject_type="LEAD", subject_id=lead.id,
        company_id=company.id if company else None, lead_id=lead.id,
        company_name=lead.company_name,
        lead_score=float(lead.lead_score or 0),
        lead_priority=getattr(lead.lead_priority, "value", lead.lead_priority),
        evidence_confidence=int(lead.evidence_confidence or 0),
        source_reliability=int(lead.source_reliability or 0),
        verification_status=getattr(lead.verification_status, "value", lead.verification_status),
        freshness_score=int(lead.freshness_score or 0),
        canonical_job_count=int(lead.it_job_count or 0),
        recent_job_count=int(lead.recent_job_count or 0),
        technologies=list(lead.technologies or []),
        hiring_roles=list(lead.hiring_roles or []),
        company_signals=list(lead.company_signals or []),
        source_count=int(lead.source_count or 0),
        last_signal_date=_iso(lead.last_signal_date),
        opportunity_summary=sanitize_text(lead.opportunity_summary),
        tenders=tenders, evidence=evidence, conflicts=conflicts, decision_makers=dms,
        provenance=getattr(lead.data_provenance, "value", "REAL"),
        generated_at=_now_iso(),
    )
