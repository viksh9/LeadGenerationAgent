"""Company-level lead pipeline: aggregate → score → persist.

Turns aggregated company hiring activity into ONE company opportunity Lead, with
a deterministic (no-LLM) score/priority, opportunity type, and an evidence trail.
`rebuild_company_leads` runs the whole thing from stored raw job records.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from config.aggregation import DEFAULT_AGGREGATION_CONFIG, AggregationConfig
from database.models import (
    DataProvenance,
    HiringIntensity,
    JobRecord,
    Lead,
    LeadPriority,
    LeadStatus,
    RawSourceRecord,
    RecordType,
    utcnow,
)
from database.repository import create_lead, find_company_lead, update_lead
from intelligence.company_aggregator import (
    CompanyAggregate,
    JobInput,
    aggregate_companies,
)

logger = logging.getLogger("intelligence")

_INTENSITY_LABEL = {
    HiringIntensity.LOW: "Low",
    HiringIntensity.MEDIUM: "Moderate",
    HiringIntensity.HIGH: "High",
    HiringIntensity.VERY_HIGH: "Very high",
}

# Opportunity type by company signal (checked in priority order).
_OPPORTUNITY_BY_SIGNAL: tuple[tuple[str, str], ...] = (
    ("VENDOR_REQUIREMENT", "Staff Augmentation"),
    ("CLOUD_MIGRATION", "Cloud Engineering Staffing"),
    ("AI_INITIATIVE", "AI/ML Engineering Staffing"),
    ("DIGITAL_TRANSFORMATION", "Digital Transformation Delivery"),
    ("LARGE_TECH_HIRING", "Staff Augmentation"),
    ("ENGINEERING_EXPANSION", "Engineering Capacity / Staffing"),
    ("RAPID_HIRING", "Engineering Capacity / Staffing"),
    ("MULTI_TECH_HIRING", "Multi-skill Technology Staffing"),
)


@dataclass
class CompanyRunSummary:
    provenance: str
    jobs: int = 0
    companies: int = 0
    created: int = 0
    updated: int = 0
    errors: list[str] = field(default_factory=list)


def score_company(agg: CompanyAggregate, config: AggregationConfig = DEFAULT_AGGREGATION_CONFIG) -> int:
    s = config.weight_intensity.get(agg.hiring_intensity.value, 0)
    s += int(config.weight_recent_ratio * agg.recent_ratio)
    s += min(len(agg.technologies) * config.weight_tech_breadth, config.weight_tech_breadth_cap)
    s += min(len(agg.company_signals) * config.weight_per_signal, config.weight_signal_cap)
    if len(agg.sources) > 1:
        s += config.weight_multi_source
    if agg.senior_count > 0:
        s += config.weight_seniority
    return max(0, min(100, s))


def priority_for(score: int, config: AggregationConfig = DEFAULT_AGGREGATION_CONFIG) -> LeadPriority:
    if score >= config.hot_threshold:
        return LeadPriority.HOT
    if score >= config.warm_threshold:
        return LeadPriority.WARM
    if score >= config.nurture_threshold:
        return LeadPriority.NURTURE
    return LeadPriority.LOW


def opportunity_type(agg: CompanyAggregate) -> str:
    for key, opp in _OPPORTUNITY_BY_SIGNAL:
        if key in agg.company_signals:
            return opp
    return "Technology Staffing"


def _summary_text(agg: CompanyAggregate, opportunity: str) -> str:
    techs = ", ".join(agg.top_technologies[:4]) or "various technologies"
    signal_str = ", ".join(s.replace("_", " ").title() for s in agg.company_signals) or "active IT hiring"
    return (
        f"{agg.display_name} has {agg.it_job_count} active IT openings "
        f"({agg.recent_job_count} in the last 30 days) across {techs}. "
        f"Signals: {signal_str}. Likely opportunity: {opportunity}."
    )


# Country-level location tokens are NOT cities — a job that only says "India" carries
# no city. We drop these from the displayed city list (unless they are all we have), so
# the UI shows real cities ("Bengaluru, Hyderabad") instead of "India +N more".
_COUNTRY_TOKENS = {"india", "bharat"}


def _hiring_cities(agg: CompanyAggregate) -> list[str]:
    """All real hiring cities, most-active first, with the bare country token removed.
    If only the country is known (no city), it is kept rather than returning nothing."""
    cities = [c.strip() for c, _ in agg.cities.most_common() if c and c.strip()]
    real = [c for c in cities if c.lower() not in _COUNTRY_TOKENS]
    return real or cities


def _location(agg: CompanyAggregate) -> Optional[str]:
    # Full, explicit city list for the UI — every real hiring city, no "+N more".
    cities = _hiring_cities(agg)
    return ", ".join(cities) if cities else None


def _location_all(agg: CompanyAggregate) -> Optional[str]:
    # Same real-city list for the Excel export.
    cities = _hiring_cities(agg)
    return ", ".join(cities) if cities else None


def _primary_source_url(agg: CompanyAggregate) -> Optional[str]:
    for ev in agg.evidence:
        if ev.get("source_url"):
            return ev["source_url"]
    return None


def _verify_company(agg: CompanyAggregate, now) -> dict:
    """Compute evidence-based verification fields for a company lead (pure).

    Kept STRICTLY separate from lead_score: a HOT lead can be PARTIALLY_VERIFIED."""
    import hashlib

    from config.evidence import VERIFICATION_VERSION
    from processors.normalization.text import normalize_for_compare
    from verification.lead_readiness import classify_readiness
    from verification.signal_verification import EvidenceInput, verify_evidence_set

    def _dt(v):
        if v is None:
            return None
        try:
            d = datetime.fromisoformat(str(v).replace("Z", "+00:00"))
            return d.astimezone(timezone.utc).replace(tzinfo=None) if d.tzinfo else d
        except (ValueError, TypeError):
            return v if isinstance(v, datetime) else None

    inputs = [
        EvidenceInput(
            source_id=e.get("source_id") or e.get("source") or "unknown",
            content_hash=hashlib.sha256(
                f"{normalize_for_compare(e.get('job_title'))}|{agg.normalized_name}".encode()
            ).hexdigest()[:32],
            source_url=e.get("source_url"),
            published_at=_dt(e.get("published_at")),
            normalized_company_name=agg.normalized_name,
            normalized_title=e.get("job_title"),
        )
        for e in agg.evidence
    ]
    signal_type = agg.company_signals[0] if agg.company_signals else "HIRING"
    result = verify_evidence_set(inputs, signal_type=signal_type, now=now)
    readiness = classify_readiness(
        verification_status=result.verification_status,
        evidence_confidence=result.evidence_confidence,
        freshness_score=result.freshness_score,
        has_meaningful_signal=agg.it_job_count > 0 or bool(agg.company_signals),
    )
    return {
        "signal_confidence": result.signal_confidence,
        "fields": {
            "source_reliability": result.source_reliability,
            "evidence_confidence": result.evidence_confidence,
            "freshness_score": result.freshness_score,
            "independent_support_count": result.independent_support_count,
            "verification_status": result.verification_status,
            "lead_readiness": readiness,
            "verification_reason": " ".join(result.reasons)[:2000],
            "verification_version": VERIFICATION_VERSION,
            "verified_at": now,
        },
    }


def build_lead_fields(
    agg: CompanyAggregate,
    *,
    config: AggregationConfig = DEFAULT_AGGREGATION_CONFIG,
    now: Optional[datetime] = None,
) -> dict:
    now = now or utcnow()
    score = score_company(agg, config)
    priority = priority_for(score, config)
    opportunity = opportunity_type(agg)
    summary = _summary_text(agg, opportunity)
    verification = _verify_company(agg, now)
    intensity_label = _INTENSITY_LABEL[agg.hiring_intensity]
    sources = sorted(agg.sources)
    pitch = (
        f"Subject: Engineering capacity for {agg.display_name}\n\n"
        f"{agg.display_name} appears to be scaling engineering ({agg.it_job_count} open IT roles, "
        f"{agg.recent_job_count} recent) in {', '.join(agg.top_technologies[:3]) or 'multiple technologies'}. "
        f"We help teams add vetted {agg.top_roles[0] if agg.top_roles else 'engineering'} capacity quickly. "
        f"Worth a short conversation with {agg.primary_target_role}?"
    )
    return {
        "company_name": agg.display_name,
        "normalized_company_name": agg.normalized_name,
        "company_domain": agg.company_domain,
        "company_type": agg.company_type,
        "industry": (agg.industries.most_common(1)[0][0] if agg.industries else None),
        "location": _location(agg),            # compact "Top +N more" for the UI
        "location_all": _location_all(agg),    # full city list for the Excel export
        "it_job_count": agg.it_job_count,
        "recent_job_count": agg.recent_job_count,
        "hiring_intensity": agg.hiring_intensity,
        "primary_target_role": agg.primary_target_role,
        "company_signals": list(agg.company_signals),
        "signal_type": agg.primary_signal,
        "signal_title": f"{intensity_label} technology hiring — {agg.it_job_count} open IT roles",
        "signal_description": summary,
        "signal_date": agg.last_signal_date,
        "last_signal_date": agg.last_signal_date,
        "source_name": f"{len(sources)} source(s): {', '.join(sources)}" if sources else None,
        "source_url": _primary_source_url(agg),
        "source_count": len(agg.sources),
        "technologies": agg.top_technologies[:12],
        "hiring_roles": agg.top_roles[:6],
        "estimated_hiring": agg.it_job_count,
        # signal_confidence is EVIDENCE-based (distinct from the commercial score).
        "signal_confidence": float(verification["signal_confidence"]),
        "lead_score": float(score),
        "lead_priority": priority,
        "opportunity_summary": summary,
        "recommended_action": f"Engage {agg.primary_target_role} about {opportunity.lower()}.",
        "recommended_pitch": pitch,
        "evidence": agg.evidence[:100],
        "data_provenance": agg.provenance,
        "status": LeadStatus.NEW,
        "last_verified_at": now,
        # Verification intelligence — kept separate from lead_score/lead_priority.
        **verification["fields"],
    }


def upsert_company_lead(
    session: Session,
    agg: CompanyAggregate,
    *,
    config: AggregationConfig = DEFAULT_AGGREGATION_CONFIG,
    now: Optional[datetime] = None,
) -> tuple[Lead, bool]:
    """Create or refresh the single company-level lead for this aggregate."""
    fields = build_lead_fields(agg, config=config, now=now)
    existing = find_company_lead(
        session, normalized_company_name=agg.normalized_name, provenance=agg.provenance
    )
    if existing is not None:
        updates = {k: v for k, v in fields.items() if k != "status"}  # keep lifecycle status
        update_lead(session, existing.id, **updates)
        return existing, False
    lead = create_lead(session, **fields)
    return lead, True


def rebuild_company_leads(
    session: Session,
    *,
    provenance: DataProvenance = DataProvenance.REAL,
    config: AggregationConfig = DEFAULT_AGGREGATION_CONFIG,
    now: Optional[datetime] = None,
    source: str = "raw",
) -> CompanyRunSummary:
    """Aggregate stored jobs of a provenance into company-level leads.

    `source="canonical"` reads deduplicated JobRecords (the real pipeline path);
    `source="raw"` reads raw_source_records directly (legacy/simple path). Real
    vs synthetic are kept strictly separate."""
    now = now or datetime.now(timezone.utc).replace(tzinfo=None)
    is_synth = provenance is DataProvenance.SYNTHETIC
    if source == "canonical":
        stmt = select(JobRecord).where(JobRecord.data_provenance == provenance)
        jobs = [JobInput.from_job_record(jr) for jr in session.scalars(stmt)]
    else:
        stmt = (
            select(RawSourceRecord)
            .where(RawSourceRecord.record_type == RecordType.JOB_POSTING)
            .where(RawSourceRecord.is_synthetic.is_(is_synth))
        )
        jobs = [JobInput.from_raw_record(r) for r in session.scalars(stmt)]
    summary = CompanyRunSummary(provenance=provenance.value, jobs=len(jobs))

    from verification.service import EvidenceVerificationService

    verifier = EvidenceVerificationService(session)
    for agg in aggregate_companies(jobs, config=config, now=now):
        try:
            lead, created = upsert_company_lead(session, agg, config=config, now=now)
            verifier.verify_lead(lead, now=now)   # persist evidence records + conflicts (idempotent)
        except Exception as exc:  # noqa: BLE001 - record, keep going
            summary.errors.append(f"{agg.display_name}: {exc}")
            continue
        summary.companies += 1
        summary.created += int(created)
        summary.updated += int(not created)

    logger.info(
        "company_rebuild provenance=%s jobs=%s companies=%s created=%s updated=%s",
        provenance.value, summary.jobs, summary.companies, summary.created, summary.updated,
    )
    return summary
