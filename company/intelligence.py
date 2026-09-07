"""Company intelligence profile aggregation from verified evidence.

Counts CANONICAL jobs (never duplicated source listings), aggregates technology /
role / location demand, computes a hiring trend (with a sample-size guard), and
surfaces signals + opportunity + evidence. Unknown stays unknown.
"""

from __future__ import annotations

from collections import Counter
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy.orm import Session

from company import repository as repo
from config.aggregation import DEFAULT_AGGREGATION_CONFIG
from database.models import Company, DataProvenance, DemandStrength, HiringTrend

_RECENT_DAYS = DEFAULT_AGGREGATION_CONFIG.recent_days
_MIN_TREND_SAMPLE = 4


def _demand_strength(active: int) -> DemandStrength:
    if active >= 6:
        return DemandStrength.HIGH
    if active >= 3:
        return DemandStrength.MEDIUM
    return DemandStrength.LOW


def _naive(dt) -> Optional[datetime]:
    if dt is None:
        return None
    return dt.astimezone(timezone.utc).replace(tzinfo=None) if dt.tzinfo else dt


def _hiring_trend(jobs, now: datetime) -> HiringTrend:
    dated = [_naive(j.published_at) for j in jobs if j.published_at]
    if len(dated) < _MIN_TREND_SAMPLE:
        return HiringTrend.UNKNOWN if len(dated) else HiringTrend.LOW_ACTIVITY
    recent = sum(1 for d in dated if d >= now - timedelta(days=_RECENT_DAYS))
    prior = sum(1 for d in dated if now - timedelta(days=2 * _RECENT_DAYS) <= d < now - timedelta(days=_RECENT_DAYS))
    if prior == 0:
        return HiringTrend.INCREASING if recent >= _MIN_TREND_SAMPLE else HiringTrend.LOW_ACTIVITY
    ratio = recent / prior
    if ratio >= 2:
        return HiringTrend.RAPIDLY_INCREASING
    if ratio >= 1.3:
        return HiringTrend.INCREASING
    if ratio <= 0.5:
        return HiringTrend.DECREASING
    return HiringTrend.STABLE


def build_company_intelligence(session: Session, company: Company, *, now: Optional[datetime] = None) -> dict:
    now = _naive(now) or datetime.now(timezone.utc).replace(tzinfo=None)
    provenance = company.data_provenance
    jobs = repo.company_jobs(session, company.normalized_name, provenance)
    signals = repo.company_signals(session, company.normalized_name, provenance)
    leads = repo.company_leads(session, company.id)
    evidence = repo.company_evidence(session, company.normalized_name)

    recent_cut = now - timedelta(days=_RECENT_DAYS)

    # Technology demand (canonical jobs only).
    tech_active: Counter = Counter()
    tech_recent: Counter = Counter()
    for j in jobs:
        pub = _naive(j.published_at)
        for t in (j.technologies or []):
            tech_active[t] += 1
            if pub and pub >= recent_cut:
                tech_recent[t] += 1
    technology_demand = [
        {"technology": t, "active_jobs": n, "recent_jobs": tech_recent.get(t, 0),
         "demand_strength": _demand_strength(n).value}
        for t, n in tech_active.most_common()
    ]

    # Role demand.
    role_active: Counter = Counter()
    for j in jobs:
        if j.normalized_role:
            role_active[j.normalized_role] += 1
    role_demand = [{"role": r, "active_jobs": n, "demand_strength": _demand_strength(n).value}
                   for r, n in role_active.most_common()]

    # Location intelligence — hiring locations (from jobs) vs office (from HQ).
    city_counts = Counter(j.city for j in jobs if j.city)
    hiring_locations = [{"city": c, "job_count": n} for c, n in city_counts.most_common()]

    lead = leads[0] if leads else None
    return {
        "identity": {
            "id": company.id, "canonical_name": company.canonical_name, "legal_name": company.legal_name,
            "primary_domain": company.primary_domain, "company_type": company.company_type.value if company.company_type else None,
            "company_types": company.company_types, "industry": company.industry,
            "identity_confidence": company.identity_confidence,
            "verification_status": company.verification_status.value,
            "data_provenance": company.data_provenance.value,
        },
        "geography": {
            "headquarters_city": company.headquarters_city, "headquarters_state": company.headquarters_state,
            "headquarters_country": company.headquarters_country,
            "india_presence": company.india_presence, "india_locations": company.india_locations,
        },
        "hiring": {
            "canonical_active_openings": len(jobs),
            "recent_openings": sum(1 for j in jobs if _naive(j.published_at) and _naive(j.published_at) >= recent_cut),
            "hiring_intensity": lead.hiring_intensity.value if lead and lead.hiring_intensity else None,
            "hiring_trend": _hiring_trend(jobs, now).value,
            "role_demand": role_demand,
        },
        "technology_demand": technology_demand,
        "location_intelligence": {
            "hiring_locations": hiring_locations,
            "office_location": company.headquarters_city,   # only asserted from HQ evidence
            "note": "Hiring location != confirmed office. Offices require explicit evidence.",
        },
        "signals": [
            {"signal_type": s.signal_type.value, "signal_title": s.signal_title,
             "strength": s.signal_strength.value, "published_at": s.published_at.isoformat() if s.published_at else None,
             "evidence_confidence": s.evidence_confidence}
            for s in signals
        ],
        "opportunity": {
            "opportunity_summary": lead.opportunity_summary if lead else None,
            "recommended_action": lead.recommended_action if lead else None,
            "lead_score": lead.lead_score if lead else None,
            "lead_priority": lead.lead_priority.value if lead else None,
            "company_signals": lead.company_signals if lead else [],
        } if lead else None,
        "evidence": {
            "verification_status": lead.verification_status.value if lead else company.verification_status.value,
            "evidence_confidence": lead.evidence_confidence if lead else company.evidence_confidence,
            "source_reliability": lead.source_reliability if lead else 0,
            "supporting_source_count": len(evidence),
            "independent_support_count": lead.independent_support_count if lead else 0,
        },
        "related_leads": [{"id": l.id, "lead_priority": l.lead_priority.value, "lead_score": l.lead_score,
                           "verification_status": l.verification_status.value} for l in leads],
    }
