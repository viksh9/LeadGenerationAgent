"""Company-level opportunity view derived from a Lead (Prompt 49).

This is the SINGLE backend derivation of the opportunity presentation shown on the
Opportunity tab. The frontend (`frontend/src/services/opportunities.ts`) derives the
same values deterministically from persisted Lead fields; this module mirrors that
exact logic so the Excel export matches the Opportunity tab (§26). It computes
nothing new and fabricates nothing — opportunity type, staffing need, and urgency
are deterministic functions of already-persisted lead fields; estimated team is the
persisted `estimated_hiring` (never invented).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from database.models import Lead, utcnow

_TYPE_LABELS = {
    "NORMAL_HIRING": "Normal Hiring",
    "PROJECT_DRIVEN_HIRING": "Project Driven Hiring",
    "LARGE_SCALE_RAMP_UP": "Large-Scale Ramp-Up",
    "STAFF_AUGMENTATION": "Staff Augmentation",
    "VENDOR_OPPORTUNITY": "Vendor Opportunity",
    "TECHNOLOGY_IMPLEMENTATION": "Technology Implementation",
    "DIGITAL_TRANSFORMATION": "Digital Transformation",
    "LOW_CONFIDENCE": "Low Confidence",
}
_DAY = 86_400


@dataclass
class OpportunityView:
    opportunity_type: str
    label: str
    staffing_need: str            # HIGH | MEDIUM | LOW | UNKNOWN
    estimated_team: int | None    # persisted estimated_hiring; None when not available
    urgency: str                  # CRITICAL | HIGH | MEDIUM | LOW | UNKNOWN
    technologies: list[str] = field(default_factory=list)
    signals: list[str] = field(default_factory=list)


def _signal_value(lead: Lead) -> str | None:
    st = lead.signal_type
    return (st.value if hasattr(st, "value") else st) if st is not None else None


def derive_staffing_need(estimated_hiring: int | None) -> str:
    if estimated_hiring is None or estimated_hiring <= 0:
        return "UNKNOWN"
    if estimated_hiring >= 25:
        return "HIGH"
    if estimated_hiring >= 10:
        return "MEDIUM"
    return "LOW"


def derive_opportunity_type(lead: Lead) -> str:
    """Mirror of frontend deriveOpportunityType (signal_type + hiring size)."""
    hiring = lead.estimated_hiring or 0
    signal = _signal_value(lead)
    if signal == "HIRING":
        base = "STAFF_AUGMENTATION" if hiring >= 10 else "NORMAL_HIRING"
    elif signal in ("PROJECT_AWARD", "PROJECT_EXECUTION"):
        base = "PROJECT_DRIVEN_HIRING"
    elif signal == "EXPANSION":
        base = "LARGE_SCALE_RAMP_UP"
    elif signal == "DIGITAL_TRANSFORMATION":
        return "DIGITAL_TRANSFORMATION"
    elif signal == "TECHNOLOGY_INITIATIVE":
        return "TECHNOLOGY_IMPLEMENTATION"
    elif signal in ("VENDOR_REQUIREMENT", "CONTRACT"):
        return "VENDOR_OPPORTUNITY"
    else:
        return "LOW_CONFIDENCE"
    if hiring >= 25:
        return "LARGE_SCALE_RAMP_UP"
    return base


def derive_urgency(signal_date: datetime | None, now: datetime) -> str:
    """Mirror of frontend deriveUrgency: recency of the signal = urgency."""
    if signal_date is None:
        return "UNKNOWN"
    # Mirror the frontend: Math.max(0, Math.floor((now - signal) / DAY)).
    days = max(0, int((now - signal_date).total_seconds() // _DAY))
    if days <= 7:
        return "CRITICAL"
    if days <= 30:
        return "HIGH"
    if days <= 60:
        return "MEDIUM"
    return "LOW"


def derive_opportunity_view(lead: Lead, *, signal_date: datetime | None = None,
                            now: datetime | None = None) -> OpportunityView:
    now = now or utcnow()
    otype = derive_opportunity_type(lead)
    techs = [str(t).strip() for t in (lead.technologies or []) if str(t).strip()]
    signals: list[str] = []
    sig = _signal_value(lead)
    if sig:
        signals.append(sig)
    for s in (lead.company_signals or []):
        s = str(s).strip()
        if s and s not in signals:
            signals.append(s)
    return OpportunityView(
        opportunity_type=otype,
        label=_TYPE_LABELS.get(otype, otype),
        staffing_need=derive_staffing_need(lead.estimated_hiring),
        estimated_team=(lead.estimated_hiring if (lead.estimated_hiring and lead.estimated_hiring > 0) else None),
        urgency=derive_urgency(signal_date, now),
        technologies=list(dict.fromkeys(techs)),
        signals=signals,
    )


def opportunity_cell(view: OpportunityView) -> str:
    """Render the Opportunity cell — the opportunity type label, as shown on the
    Opportunities tab. Staffing / Est. Team / Urgency are intentionally omitted."""
    return view.label
