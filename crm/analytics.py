"""CRM analytics from REAL data only (§24, §25, §26, §60).

Every number is computed from actual database records/activities. Conversion
rates are returned ONLY when the denominator has real events, otherwise the metric
is ``INSUFFICIENT_DATA`` — denominators are never fabricated. Pipeline value is
summed ONLY from opportunities whose value has a legitimate source (USER/EVIDENCE);
if none exist the value is ``NOT_AVAILABLE`` — revenue is never inferred from job
counts or lead scores.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from database.models import (
    ActivityType,
    CRMActivity,
    DataProvenance,
    Lead,
    LeadStatus,
    SalesOpportunity,
    SalesStage,
    utcnow,
)

INSUFFICIENT_DATA = "INSUFFICIENT_DATA"
NOT_AVAILABLE = "NOT_AVAILABLE"

# Lead funnel order — statuses only advance on real events (enforced by lifecycle),
# so counting "at or beyond" a stage is an honest funnel measure.
_FUNNEL = [
    LeadStatus.OUTREACH_READY, LeadStatus.CONTACTED, LeadStatus.REPLIED, LeadStatus.MEETING,
    LeadStatus.QUALIFIED, LeadStatus.PROPOSAL, LeadStatus.WON,
]
_RANK = {s: i for i, s in enumerate([
    LeadStatus.NEW, LeadStatus.RESEARCHED, LeadStatus.OUTREACH_READY, LeadStatus.CONTACTED,
    LeadStatus.REPLIED, LeadStatus.MEETING, LeadStatus.QUALIFIED, LeadStatus.PROPOSAL, LeadStatus.WON,
])}
# LOST/NURTURE/DISQUALIFIED sit outside the linear funnel.
_TERMINAL_RANK = _RANK[LeadStatus.WON]


@dataclass
class ConversionMetric:
    label: str
    numerator: int
    denominator: int
    # rate is a float in [0,1], or the string INSUFFICIENT_DATA when denominator == 0
    rate: float | str

    def as_dict(self) -> dict:
        return {"label": self.label, "numerator": self.numerator,
                "denominator": self.denominator, "rate": self.rate}


@dataclass
class CRMAnalytics:
    generated_at: datetime
    total_leads: int
    lead_status_counts: dict[str, int]
    sales_stage_counts: dict[str, int]
    activity_counts: dict[str, int]
    real_contacted: int
    real_replies: int
    real_meetings: int
    conversion: list[ConversionMetric]
    pipeline_value: float | str          # sum or NOT_AVAILABLE
    pipeline_value_currency: str | None
    pipeline_value_opportunities: int    # how many opps contributed a real value
    open_opportunities: int
    won: int
    lost: int

    def as_dict(self) -> dict:
        return {
            "generated_at": self.generated_at.isoformat(),
            "total_leads": self.total_leads,
            "lead_status_counts": self.lead_status_counts,
            "sales_stage_counts": self.sales_stage_counts,
            "activity_counts": self.activity_counts,
            "real_contacted": self.real_contacted,
            "real_replies": self.real_replies,
            "real_meetings": self.real_meetings,
            "conversion": [c.as_dict() for c in self.conversion],
            "pipeline_value": self.pipeline_value,
            "pipeline_value_currency": self.pipeline_value_currency,
            "pipeline_value_opportunities": self.pipeline_value_opportunities,
            "open_opportunities": self.open_opportunities,
            "won": self.won,
            "lost": self.lost,
        }


def _count(session, model, *where) -> int:
    stmt = select(func.count()).select_from(model)
    for w in where:
        stmt = stmt.where(w)
    return int(session.execute(stmt).scalar() or 0)


def _rate(numerator: int, denominator: int) -> float | str:
    if denominator <= 0:
        return INSUFFICIENT_DATA
    return round(numerator / denominator, 4)


def compute_crm_analytics(session: Session, *, now: datetime | None = None) -> CRMAnalytics:
    now = now or utcnow()

    # Lead status distribution (real leads only).
    status_rows = session.execute(
        select(Lead.status, func.count(Lead.id))
        .where(Lead.data_provenance == DataProvenance.REAL).group_by(Lead.status)
    ).all()
    status_counts: dict[str, int] = {}
    for st, n in status_rows:
        status_counts[st.value if hasattr(st, "value") else str(st)] = int(n)
    total_leads = sum(status_counts.values())

    # "At or beyond" funnel counts from real statuses.
    def at_or_beyond(stage: LeadStatus) -> int:
        threshold = _RANK[stage]
        total = 0
        for st_value, n in status_counts.items():
            try:
                st = LeadStatus(st_value)
            except ValueError:
                continue
            if st in _RANK and _RANK[st] >= threshold:
                total += n
        return total

    outreach_ready = at_or_beyond(LeadStatus.OUTREACH_READY)
    contacted = at_or_beyond(LeadStatus.CONTACTED)
    replied = at_or_beyond(LeadStatus.REPLIED)
    meeting = at_or_beyond(LeadStatus.MEETING)
    qualified = at_or_beyond(LeadStatus.QUALIFIED)
    proposal = at_or_beyond(LeadStatus.PROPOSAL)
    won = status_counts.get(LeadStatus.WON.value, 0)
    lost = status_counts.get(LeadStatus.LOST.value, 0)

    conversion = [
        ConversionMetric("contact_rate", contacted, outreach_ready, _rate(contacted, outreach_ready)),
        ConversionMetric("reply_rate", replied, contacted, _rate(replied, contacted)),
        ConversionMetric("meeting_rate", meeting, replied, _rate(meeting, replied)),
        ConversionMetric("qualification_rate", qualified, meeting, _rate(qualified, meeting)),
        ConversionMetric("proposal_rate", proposal, qualified, _rate(proposal, qualified)),
        ConversionMetric("win_rate", won, proposal, _rate(won, proposal)),
    ]

    # Real activity counts (provider/human events).
    activity_rows = session.execute(
        select(CRMActivity.activity_type, func.count(CRMActivity.id)).group_by(CRMActivity.activity_type)
    ).all()
    activity_counts = {(t.value if hasattr(t, "value") else str(t)): int(n) for t, n in activity_rows}
    real_contacted = _count(session, CRMActivity, CRMActivity.activity_type == ActivityType.EMAIL,
                            CRMActivity.status == "SENT")
    real_replies = activity_counts.get(ActivityType.EMAIL_REPLY.value, 0)
    real_meetings = activity_counts.get(ActivityType.MEETING.value, 0)

    # Sales pipeline stage distribution.
    stage_rows = session.execute(
        select(SalesOpportunity.stage, func.count(SalesOpportunity.id)).group_by(SalesOpportunity.stage)
    ).all()
    stage_counts = {(s.value if hasattr(s, "value") else str(s)): int(n) for s, n in stage_rows}
    open_opps = sum(n for s, n in stage_counts.items()
                    if s not in (SalesStage.WON.value, SalesStage.LOST.value))

    # Pipeline value — ONLY from opportunities with a legitimate value source.
    value_rows = session.execute(
        select(SalesOpportunity.estimated_value, SalesOpportunity.estimated_value_currency)
        .where(
            SalesOpportunity.estimated_value.is_not(None),
            SalesOpportunity.value_source.in_(["USER", "EVIDENCE"]),
        )
    ).all()
    if value_rows:
        pipeline_value: float | str = round(sum(float(v) for v, _ in value_rows), 2)
        currency = next((c for _, c in value_rows if c), None)
        value_count = len(value_rows)
    else:
        pipeline_value = NOT_AVAILABLE     # never inferred (§26)
        currency = None
        value_count = 0

    return CRMAnalytics(
        generated_at=now, total_leads=total_leads, lead_status_counts=status_counts,
        sales_stage_counts=stage_counts, activity_counts=activity_counts,
        real_contacted=real_contacted, real_replies=real_replies, real_meetings=real_meetings,
        conversion=conversion, pipeline_value=pipeline_value, pipeline_value_currency=currency,
        pipeline_value_opportunities=value_count, open_opportunities=open_opps, won=won, lost=lost,
    )
