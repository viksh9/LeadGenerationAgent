"""Deterministic, evidence-grounded summaries (Prompt 50, §14 / §19).

Both the Signal Summary and the Company Profile Summary are computed ONLY from
already-persisted real fields — opening counts, technologies, signal type, company
facts. They never add a claim that the underlying data does not support, and they
degrade to a shorter honest phrase (or empty) when evidence is missing rather than
inventing filler. India relevance is surfaced only when the real location says so.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from database.models import Company, Lead
from intelligence.opportunity_view import OpportunityView, derive_staffing_need

# Human labels for the signal_type enum (real signal categories only).
_SIGNAL_LABELS = {
    "HIRING": "technology hiring",
    "PROJECT_AWARD": "project award",
    "PROJECT_EXECUTION": "project execution",
    "EXPANSION": "expansion",
    "DIGITAL_TRANSFORMATION": "digital transformation",
    "TECHNOLOGY_INITIATIVE": "technology initiative",
    "VENDOR_REQUIREMENT": "vendor requirement",
    "CONTRACT": "contract",
    "ACQUISITION": "acquisition",
}


def _opening_count(lead: Lead) -> Optional[int]:
    for value in (lead.it_job_count, lead.estimated_hiring, lead.recent_job_count):
        if value and value > 0:
            return int(value)
    return None


def _tech_list(lead: Lead, limit: int = 4) -> list[str]:
    seen: list[str] = []
    for t in (lead.technologies or []):
        t = str(t).strip()
        if t and t not in seen:
            seen.append(t)
        if len(seen) >= limit:
            break
    return seen


def build_signal_summary(lead: Lead) -> str:
    """A one-line summary of the ACTUAL hiring/business signal. Empty string when
    there is no supporting evidence (caller shows "Signal Unavailable")."""
    signal = lead.signal_type.value if hasattr(lead.signal_type, "value") else lead.signal_type
    openings = _opening_count(lead)
    techs = _tech_list(lead)

    label = _SIGNAL_LABELS.get(signal or "", None)
    parts: list[str] = []

    if openings is not None:
        need = derive_staffing_need(openings)
        intensity = {"HIGH": "High", "MEDIUM": "Moderate", "LOW": "Limited"}.get(need, "")
        head = f"{intensity} {label}".strip() if label else (intensity or "Active hiring")
        parts.append(f"{head} — {openings} open IT role{'s' if openings != 1 else ''}")
    elif label:
        parts.append(label.capitalize())

    if techs:
        parts.append("across " + ", ".join(techs))

    return " ".join(parts).strip()


@dataclass
class CompanyProfileSummary:
    """Structured company profile from REAL fields only (blanks stay blank, §19)."""

    company_name: Optional[str] = None
    industry: Optional[str] = None
    india_presence: str = "UNKNOWN"          # Yes | No | UNKNOWN
    india_entity_type: Optional[str] = None
    website: Optional[str] = None
    primary_location: Optional[str] = None
    registered_location: Optional[str] = None
    career_site: Optional[str] = None
    technology_focus: list[str] = field(default_factory=list)
    current_hiring_signal: Optional[str] = None
    opportunity: Optional[str] = None
    data_trust: int = 0
    headline: str = ""

    def as_dict(self) -> dict:
        return {
            "company_name": self.company_name, "industry": self.industry,
            "india_presence": self.india_presence, "india_entity_type": self.india_entity_type,
            "website": self.website, "primary_location": self.primary_location,
            "registered_location": self.registered_location, "career_site": self.career_site,
            "technology_focus": self.technology_focus, "current_hiring_signal": self.current_hiring_signal,
            "opportunity": self.opportunity, "data_trust": self.data_trust, "headline": self.headline,
        }


def _india_presence(company: Optional[Company]) -> str:
    if company is None or company.india_presence is None:
        return "UNKNOWN"
    return "Yes" if company.india_presence else "No"


def build_company_profile(lead: Lead, company: Optional[Company], *,
                          opportunity: Optional[OpportunityView] = None,
                          data_trust: int = 0) -> CompanyProfileSummary:
    """Assemble the company profile from real Company + Lead fields. Never invents a
    company description; the headline is a deterministic join of present facts."""
    industry = (company.industry if company else None) or lead.industry
    website = (company.website if company else None) or lead.company_website
    primary_location = (company.full_address if company else None) or lead.location
    registered_location = company.registered_address if company else None
    career_site = company.careers_url if company else None
    techs = _tech_list(lead, limit=8)

    profile = CompanyProfileSummary(
        company_name=(company.canonical_name if company else None) or lead.company_name,
        industry=industry,
        india_presence=_india_presence(company),
        india_entity_type=(company.india_entity_type if company else None),
        website=website,
        primary_location=primary_location,
        registered_location=registered_location,
        career_site=career_site,
        technology_focus=techs,
        current_hiring_signal=build_signal_summary(lead) or None,
        opportunity=(opportunity.label if opportunity else None),
        data_trust=int(data_trust or 0),
    )

    bits: list[str] = []
    if profile.company_name:
        bits.append(profile.company_name)
    if industry:
        bits.append(f"({industry})")
    if profile.india_presence == "Yes" and primary_location:
        bits.append(f"— India presence in {primary_location}")
    elif profile.india_presence == "Yes":
        bits.append("— India presence")
    if profile.opportunity:
        bits.append(f"· {profile.opportunity}")
    profile.headline = " ".join(bits).strip()
    return profile
