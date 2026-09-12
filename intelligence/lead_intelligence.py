"""Lead Intelligence aggregation (Prompt 50, §1 / §43).

The final read-model that composes REAL company + signal + opportunity + POC data into
one traceable intelligence view. It is an aggregator, not a new scoring engine: every
number it returns comes from an existing engine —

    Data Trust     -> Company.data_trust_score            (official_company/trust.py)
    Contact Trust  -> DecisionMaker.contact_trust_score   (contact_enrichment / public trust)
    Role Match     -> DecisionMaker.role_match_score       (contact_enrichment)
    Lead Score     -> Lead.lead_score / lead_priority      (lead_scorer)
    Freshness      -> DecisionMaker.freshness_score         (verification/freshness)
    POC Status     -> derive_poc_status                     (intelligence/poc_status)
    Opportunity    -> derive_opportunity_view               (opportunity_view)
    Summaries      -> intelligence/summaries
    AI Highlights  -> ai/highlights over the validated AIIntelligenceResult

POC intelligence is company/opportunity level (one set of POCs per company, never per
job — §1). Nothing here fabricates: a lead with no real person yields recommended roles
only (RECOMMENDED_ROLE_ONLY), never an invented contact.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from ai import service as ai_service
from ai.highlights import ProfileHighlights, build_profile_highlights
from database.models import (
    Company,
    CompanyFieldEvidence,
    DecisionMaker,
    Lead,
    utcnow,
)
from enrichment.contactout_poc import resolve_company_for_lead
from enrichment.stakeholder import recommend_for_lead
from intelligence.opportunity_view import OpportunityView, derive_opportunity_view
from intelligence.poc_status import derive_poc_status
from intelligence.summaries import CompanyProfileSummary, build_company_profile, build_signal_summary


@dataclass
class SourceRef:
    """One contributing source for a field (§11/§34). Only real, contributing sources
    are ever included — never every configured provider."""

    field: str
    value: Optional[str]
    source: str
    source_type: Optional[str] = None
    source_url: Optional[str] = None
    source_record_id: Optional[str] = None
    trust_score: int = 0
    verification_status: Optional[str] = None
    evidence: Optional[str] = None
    retrieved_at: Optional[str] = None
    last_verified_at: Optional[str] = None

    def as_dict(self) -> dict:
        return {k: getattr(self, k) for k in (
            "field", "value", "source", "source_type", "source_url", "source_record_id",
            "trust_score", "verification_status", "evidence", "retrieved_at", "last_verified_at")}


@dataclass
class POCIntelligence:
    poc: DecisionMaker
    poc_status: str
    role_match_score: int
    contact_trust_score: int
    contact_trust_status: Optional[str]
    is_primary: bool


@dataclass
class LeadIntelligence:
    lead_id: int
    company_id: Optional[int]
    company_name: Optional[str]
    lead_score: float
    lead_priority: Optional[str]
    data_trust: int
    contact_trust: int
    signal_summary: str
    company_profile: CompanyProfileSummary
    opportunity: OpportunityView
    recommended_roles: list
    recommendation_confidence: int
    primary_poc: Optional[POCIntelligence]
    secondary_pocs: list[POCIntelligence]
    ai_highlights: ProfileHighlights
    sources: list[SourceRef]
    freshness_score: int
    freshness_status: str           # FRESH | AGING | STALE | UNKNOWN
    sales_action: str
    generated_at: str


def _enum(v):
    return v.value if hasattr(v, "value") else v


def _company_pocs(session: Session, company_id: Optional[int]) -> list[DecisionMaker]:
    """All REAL person POCs for the company, any source (§1 — company level). Ranked by
    role match then contact trust. Deduplication is enforced upstream by the
    (company_id, normalized_name, normalized_role) unique constraint."""
    if company_id is None:
        return []
    from database.models import DataProvenance
    rows = session.scalars(select(DecisionMaker).where(
        DecisionMaker.company_id == company_id,
        DecisionMaker.full_name.isnot(None),
        DecisionMaker.data_provenance == DataProvenance.REAL,
    )).all()
    return sorted(rows, key=lambda d: ((d.role_match_score or d.match_score or 0),
                                       (d.contact_trust_score or 0)), reverse=True)


def _freshness_status(dm: Optional[DecisionMaker], *, now: datetime) -> tuple[int, str]:
    if dm is None:
        return 0, "UNKNOWN"
    from intelligence.poc_status import is_stale
    score = int(dm.freshness_score or 0)
    if is_stale(dm, now=now):
        return score, "STALE"
    if score >= 78:
        return score, "FRESH"
    if score > 0:
        return score, "AGING"
    return score, "UNKNOWN"


def _sales_action(opportunity: OpportunityView, primary: Optional[POCIntelligence],
                  roles: list) -> str:
    """Evidence-based recommended sales action (§29/§30). Uses only the opportunity type
    and the recommended/real role — never asserts the company requested services."""
    target = None
    if primary is not None and primary.poc.job_title:
        target = primary.poc.job_title
    elif roles:
        target = roles[0].role
    otype = opportunity.opportunity_type
    verb = {
        "STAFF_AUGMENTATION": "Recommended outreach to {t} regarding staff augmentation capacity",
        "LARGE_SCALE_RAMP_UP": "Recommended outreach to {t} regarding large-scale delivery capacity",
        "VENDOR_OPPORTUNITY": "Explore vendor engagement with {t}",
        "TECHNOLOGY_IMPLEMENTATION": "Engage {t} regarding technology implementation support",
        "DIGITAL_TRANSFORMATION": "Engage {t} regarding digital transformation delivery",
        "PROJECT_DRIVEN_HIRING": "Engage {t} regarding project delivery capacity",
        "NORMAL_HIRING": "Engage {t} regarding current technology hiring",
    }.get(otype, "Recommended outreach to {t} based on current hiring evidence")
    if not target:
        return "Evidence indicates a potential opportunity; identify the relevant decision-maker role before outreach."
    return verb.format(t=target)


def _company_sources(session: Session, company: Optional[Company]) -> list[SourceRef]:
    if company is None:
        return []
    rows = session.scalars(select(CompanyFieldEvidence).where(
        CompanyFieldEvidence.company_id == company.id).order_by(
        CompanyFieldEvidence.field, CompanyFieldEvidence.source_priority)).all()
    out: list[SourceRef] = []
    for e in rows:
        out.append(SourceRef(
            field=e.field, value=e.value, source=e.source, source_type=e.source_type,
            source_url=e.source_url, trust_score=int(e.trust_score or 0),
            evidence=e.evidence_text,
            retrieved_at=e.retrieved_at.isoformat() if e.retrieved_at else None,
            last_verified_at=e.last_verified_at.isoformat() if e.last_verified_at else None))
    return out


def lead_sources(session: Session, lead: Lead) -> list[SourceRef]:
    """All contributing sources for a lead (§11/§35): company field evidence + the
    lead's own signal source + each real POC's contact source. Only real values."""
    company, company_name, _ = resolve_company_for_lead(session, lead)
    out = _company_sources(session, company)
    if lead.source_name or lead.source_url:
        from export.excel import _clean_source
        source_label = _clean_source(lead.source_name) or "Signal source"
        out.append(SourceRef(
            field="signal", value=lead.signal_title or lead.signal_description,
            source=source_label, source_type="signal",
            source_url=lead.source_url,
            last_verified_at=lead.last_signal_date.isoformat() if lead.last_signal_date else None))
    for dm in _company_pocs(session, company.id if company else None):
        if dm.contact_source:
            out.append(SourceRef(
                field=f"poc:{dm.full_name}", value=dm.job_title, source=dm.contact_source,
                source_type=dm.source_type, source_url=dm.source_url,
                source_record_id=dm.source_record_id,
                trust_score=int(dm.contact_trust_score or 0),
                verification_status=_enum(dm.verification_status),
                last_verified_at=dm.last_verified_at.isoformat() if dm.last_verified_at else None))
    return out


def build_lead_intelligence(session: Session, lead: Lead, *, refresh: bool = False,
                            now: Optional[datetime] = None) -> LeadIntelligence:
    now = now or utcnow()
    company, company_name, _domain = resolve_company_for_lead(session, lead)
    opportunity = derive_opportunity_view(lead, signal_date=lead.last_signal_date, now=now)

    # POCs — company level, ranked, with derived status (§1/§7/§21).
    people = _company_pocs(session, company.id if company else None)
    poc_intel: list[POCIntelligence] = []
    for i, dm in enumerate(people):
        poc_intel.append(POCIntelligence(
            poc=dm, poc_status=derive_poc_status(dm, now=now),
            role_match_score=int(dm.role_match_score or dm.match_score or 0),
            contact_trust_score=int(dm.contact_trust_score or 0),
            contact_trust_status=dm.contact_trust_status, is_primary=(i == 0)))
    primary = poc_intel[0] if poc_intel else None
    secondary = poc_intel[1:3]

    rec = recommend_for_lead(lead)
    roles = rec.recommended_roles
    data_trust = int(company.data_trust_score or 0) if company else 0
    contact_trust = primary.contact_trust_score if primary else 0
    profile = build_company_profile(lead, company, opportunity=opportunity, data_trust=data_trust)

    # AI highlights over the cached/validated AI result (deterministic if AI off). The
    # GET path never forces a provider call; refresh re-runs analysis (bounded).
    ai_result = ai_service.analyze_lead(session, lead, force=refresh)
    source_labels = sorted({s.source for s in lead_sources(session, lead) if s.source})
    highlights = build_profile_highlights(
        lead, ai_result=ai_result, opportunity=opportunity,
        source_ids=source_labels, source_count=len(source_labels))

    fresh_score, fresh_status = _freshness_status(primary.poc if primary else None, now=now)

    return LeadIntelligence(
        lead_id=lead.id, company_id=(company.id if company else None), company_name=company_name,
        lead_score=float(lead.lead_score or 0), lead_priority=_enum(lead.lead_priority),
        data_trust=data_trust, contact_trust=contact_trust,
        signal_summary=build_signal_summary(lead), company_profile=profile, opportunity=opportunity,
        recommended_roles=roles, recommendation_confidence=rec.recommendation_confidence,
        primary_poc=primary, secondary_pocs=secondary, ai_highlights=highlights,
        sources=lead_sources(session, lead), freshness_score=fresh_score, freshness_status=fresh_status,
        sales_action=_sales_action(opportunity, primary, roles),
        generated_at=now.isoformat())
