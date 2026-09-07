"""CompanySignalAggregator: combine job + business intelligence per company into
conservative OpportunityCandidates.

The competitive core: hiring activity AND a business signal (e.g. a new project +
engineering openings) is a stronger opportunity than either alone. Nothing is
promoted to a Lead here — candidates carry the inputs the scorer consumes.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from config.aggregation import DEFAULT_AGGREGATION_CONFIG, AggregationConfig
from database.models import (
    BusinessSignal,
    BusinessSignalType,
    DataProvenance,
    HiringIntensity,
    JobRecord,
    OpportunityCandidate,
    OpportunityStatus,
    SignalStrength,
)
from intelligence.company_aggregator import CompanyAggregate, JobInput, aggregate_companies

logger = logging.getLogger("intelligence")

_PROJECT = {BusinessSignalType.PROJECT_AWARD, BusinessSignalType.PROJECT_EXECUTION}
_CONTRACT = {BusinessSignalType.CONTRACT, BusinessSignalType.TENDER}
_TRANSFORM = {BusinessSignalType.DIGITAL_TRANSFORMATION, BusinessSignalType.CLOUD_MIGRATION,
              BusinessSignalType.TECHNOLOGY_MODERNIZATION, BusinessSignalType.AI_INITIATIVE}
_EXPANSION = {BusinessSignalType.EXPANSION, BusinessSignalType.DELIVERY_CENTER_EXPANSION,
              BusinessSignalType.ENGINEERING_EXPANSION}

_OPPORTUNITY_BY_SIGNAL: list[tuple[set, str]] = [
    ({BusinessSignalType.VENDOR_REQUIREMENT, BusinessSignalType.OUTSOURCING}, "Staff Augmentation"),
    ({BusinessSignalType.CLOUD_MIGRATION}, "Cloud Engineering"),
    ({BusinessSignalType.AI_INITIATIVE}, "AI/ML Engineering"),
    (_TRANSFORM, "Digital Transformation Delivery"),
    (_CONTRACT, "Technology Implementation / Staffing"),
    (_PROJECT, "Technology Implementation / Staffing"),
    (_EXPANSION, "Engineering Capacity"),
]


@dataclass
class CandidateRunSummary:
    provenance: str
    candidates: int = 0
    review: int = 0


def _recent(sig: BusinessSignal, config: AggregationConfig) -> bool:
    return sig.signal_age_days is not None and sig.signal_age_days <= config.recent_days


def _it_company(job_agg: Optional[CompanyAggregate], techs: set) -> tuple[str, int]:
    if job_agg is not None and (job_agg.company_type.value != "OTHER_TECHNOLOGY" or job_agg.technologies):
        return ("true", 80)
    if techs:
        return ("true", 55)
    return ("unknown", 30)


def _opportunity_types(signal_types: set, has_jobs: bool) -> list[str]:
    types: list[str] = []
    for keys, label in _OPPORTUNITY_BY_SIGNAL:
        if signal_types & keys and label not in types:
            types.append(label)
    if has_jobs and "Technology Staffing" not in types and not types:
        types.append("Technology Staffing")
    if has_jobs and not types:
        types.append("Technology Staffing")
    return types or (["Technology Staffing"] if has_jobs else ["Under Review"])


def build_opportunity_candidates(
    session: Session,
    *,
    provenance: DataProvenance = DataProvenance.REAL,
    config: AggregationConfig = DEFAULT_AGGREGATION_CONFIG,
    now: Optional[datetime] = None,
) -> CandidateRunSummary:
    now = now or datetime.now(timezone.utc).replace(tzinfo=None)

    # Business signals grouped by company.
    biz: dict[str, list[BusinessSignal]] = {}
    for sig in session.scalars(select(BusinessSignal).where(BusinessSignal.data_provenance == provenance)):
        if sig.normalized_company_name:
            biz.setdefault(sig.normalized_company_name, []).append(sig)

    # Job intelligence per company (from canonical JobRecords).
    job_inputs = [JobInput.from_job_record(jr) for jr in session.scalars(
        select(JobRecord).where(JobRecord.data_provenance == provenance)
    )]
    job_aggs = {a.normalized_name: a for a in aggregate_companies(job_inputs, config=config, now=now)}

    # Rebuild candidates for this provenance.
    session.execute(delete(OpportunityCandidate).where(OpportunityCandidate.data_provenance == provenance))
    summary = CandidateRunSummary(provenance=provenance.value)

    for norm in set(biz) | set(job_aggs):
        signals = biz.get(norm, [])
        jagg = job_aggs.get(norm)
        candidate = _build(norm, signals, jagg, config, now, provenance)
        if candidate is None:
            continue
        session.add(candidate)
        summary.candidates += 1
        if candidate.status is OpportunityStatus.REVIEW:
            summary.review += 1

    session.commit()
    logger.info("opportunity_candidates provenance=%s candidates=%s review=%s",
                provenance.value, summary.candidates, summary.review)
    return summary


def _build(norm, signals, jagg, config, now, provenance) -> Optional[OpportunityCandidate]:
    signal_types = {s.signal_type for s in signals}
    strong_signals = sum(1 for s in signals if s.signal_strength is SignalStrength.STRONG)
    recent_signals = sum(1 for s in signals if _recent(s, config))
    project_signals = sum(1 for s in signals if s.signal_type in _PROJECT)
    contract_signals = sum(1 for s in signals if s.signal_type in _CONTRACT)
    transform_signals = sum(1 for s in signals if s.signal_type in _TRANSFORM)
    expansion_signals = sum(1 for s in signals if s.signal_type in _EXPANSION)
    last_signal = max((s.published_at for s in signals if s.published_at), default=None)
    evidence = max((s.evidence_confidence for s in signals), default=0)
    biz_sources = {r.source_id for s in signals for r in s.source_references}

    it_job_count = jagg.it_job_count if jagg else 0
    recent_jobs = jagg.recent_job_count if jagg else 0
    intensity = jagg.hiring_intensity if jagg else None
    top_tech = jagg.top_technologies[:12] if jagg else []
    job_sources = set(jagg.sources) if jagg else set()
    display = jagg.display_name if jagg else (signals[0].company_name if signals else norm)
    domain = (jagg.company_domain if jagg else None) or next((s.company_domain for s in signals if s.company_domain), None)

    techs = set(top_tech) | {t for s in signals for t in (s.technology_terms or [])}
    it_status, it_conf = _it_company(jagg, techs)

    # Conservative gating (§26/§28).
    strong_hiring = intensity in (HiringIntensity.HIGH, HiringIntensity.VERY_HIGH)
    has_strong_business = strong_signals > 0 or (project_signals + contract_signals) > 0
    combination = it_job_count > 0 and len(signals) > 0
    meaningful = strong_hiring or has_strong_business or combination or it_job_count >= config.intensity_medium

    if not meaningful:
        # Not enough evidence for a candidate — skip a lone old job / bare partnership.
        return None

    # Confidence (0-100) — inputs for the Lead scorer, not a final lead score.
    conf = 0
    conf += {HiringIntensity.VERY_HIGH: 35, HiringIntensity.HIGH: 28, HiringIntensity.MEDIUM: 18,
             HiringIntensity.LOW: 8}.get(intensity, 0)
    conf += min(strong_signals * 14, 28)
    conf += min((project_signals + contract_signals) * 8, 16)
    conf += min(transform_signals * 6, 12)
    conf += 12 if combination else 0
    conf += 6 if len(biz_sources) > 1 else 0
    conf = min(100, conf)

    reason_bits = []
    if it_job_count:
        reason_bits.append(f"{it_job_count} IT openings ({recent_jobs} recent)")
    if signals:
        reason_bits.append(f"{len(signals)} business signal(s): " + ", ".join(sorted({s.signal_type.value for s in signals})))
    reason = "; ".join(reason_bits) or "insufficient evidence"

    status = OpportunityStatus.CANDIDATE if (combination or has_strong_business or strong_hiring) and conf >= 30 \
        else OpportunityStatus.REVIEW

    return OpportunityCandidate(
        company_name=display, normalized_company_name=norm, company_domain=domain,
        data_provenance=provenance,
        it_company_status=it_status, it_company_confidence=it_conf,
        it_job_count=it_job_count, recent_it_jobs=recent_jobs, hiring_intensity=intensity,
        top_technologies=top_tech,
        total_business_signals=len(signals), recent_business_signals=recent_signals,
        strong_signals=strong_signals, project_signals=project_signals, contract_signals=contract_signals,
        transformation_signals=transform_signals, expansion_signals=expansion_signals,
        opportunity_types=_opportunity_types(signal_types, it_job_count > 0),
        signal_types=sorted({s.signal_type.value for s in signals}),
        reason=reason, source_count=len(job_sources | biz_sources),
        evidence_confidence=evidence, confidence=conf, last_signal_date=last_signal, status=status,
    )
