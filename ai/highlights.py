"""AI Profile Highlights (Prompt 50, §15-§18, §40-§42).

Highlights are a small, structured, evidence-grounded view for the lead-detail UI.
They come in two flavours, and the split is the whole point:

  * DETERMINISTIC highlights (Hiring Trend, Technology Focus, Hiring Signal,
    Potential Opportunity) are computed straight from real persisted fields. They are
    NOT AI output — they are always present and never fabricated.
  * The AI INSIGHT highlight is the only AI-authored line. It is sourced from the
    already-validated ``AIIntelligenceResult`` (the AI layer's grounding validator has
    already downgraded any unsupported claim). It is shown ONLY when the result was
    actually AI-generated; when the AI provider is unavailable we surface
    "AI Profile Highlights unavailable" — never hard-coded fallback prose (§42).

Every highlight carries its supporting signal/source references and a trust level
(HIGH / MEDIUM / LOW) derived from real evidence strength (§17), never a flat 100%.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from database.models import AIAnalysisStatus, AIIntelligenceResult, Lead
from intelligence.opportunity_view import OpportunityView, derive_staffing_need
from intelligence.summaries import build_signal_summary

TRUST_HIGH = "HIGH"
TRUST_MEDIUM = "MEDIUM"
TRUST_LOW = "LOW"

_AI_UNAVAILABLE_TEXT = "AI Profile Highlights unavailable."
# Sources that count as strong/official corroboration for trust levelling (§17).
_OFFICIAL_SOURCE_TOKENS = ("official", "career", "greenhouse", "lever", "government", "registry")


@dataclass
class ProfileHighlight:
    highlight_title: str
    highlight_text: str
    trust_level: str = TRUST_MEDIUM
    supporting_signal_ids: list[int] = field(default_factory=list)
    supporting_source_ids: list[str] = field(default_factory=list)
    ai_generated: bool = False

    def as_dict(self) -> dict:
        return {
            "highlight_title": self.highlight_title, "highlight_text": self.highlight_text,
            "trust_level": self.trust_level, "supporting_signal_ids": self.supporting_signal_ids,
            "supporting_source_ids": self.supporting_source_ids, "ai_generated": self.ai_generated,
        }


@dataclass
class ProfileHighlights:
    highlights: list[ProfileHighlight] = field(default_factory=list)
    ai_available: bool = False
    ai_insight: Optional[str] = None       # None => "unavailable" state
    model_version: Optional[str] = None
    generated_at: Optional[str] = None

    def as_dict(self) -> dict:
        return {
            "highlights": [h.as_dict() for h in self.highlights],
            "ai_available": self.ai_available, "ai_insight": self.ai_insight,
            "model_version": self.model_version, "generated_at": self.generated_at,
        }


def _has_official_source(source_ids: list[str]) -> bool:
    return any(any(tok in (s or "").lower() for tok in _OFFICIAL_SOURCE_TOKENS) for s in source_ids)


def evidence_trust_level(*, source_ids: list[str], source_count: int) -> str:
    """§17: HIGH = official/career data + a second source; MEDIUM = one reliable
    source; LOW = weak/indirect. Derived only from real corroboration counts."""
    official = _has_official_source(source_ids)
    n = max(source_count, len(source_ids))
    if official and n >= 2:
        return TRUST_HIGH
    if official or n >= 2:
        return TRUST_MEDIUM
    return TRUST_LOW


def _opening_count(lead: Lead) -> Optional[int]:
    for value in (lead.it_job_count, lead.estimated_hiring, lead.recent_job_count):
        if value and value > 0:
            return int(value)
    return None


def build_profile_highlights(lead: Lead, *, ai_result: Optional[AIIntelligenceResult] = None,
                             opportunity: Optional[OpportunityView] = None,
                             source_ids: Optional[list[str]] = None,
                             source_count: int = 0) -> ProfileHighlights:
    """Compose deterministic highlights (always) + one AI insight (only when the AI
    result was genuinely AI-generated and grounded)."""
    source_ids = list(source_ids or [])
    trust = evidence_trust_level(source_ids=source_ids, source_count=source_count)
    signal_ids = sorted({int(e) for e in (ai_result.evidence_ids if ai_result else []) if isinstance(e, int)})

    out = ProfileHighlights()

    # --- Deterministic, always-present highlights (real data only) ---------- #
    openings = _opening_count(lead)
    if openings is not None:
        need = derive_staffing_need(openings)
        trend = {"HIGH": "High", "MEDIUM": "Moderate", "LOW": "Limited"}.get(need, "Active")
        out.highlights.append(ProfileHighlight(
            highlight_title="Hiring Trend", highlight_text=trend, trust_level=trust,
            supporting_signal_ids=signal_ids, supporting_source_ids=source_ids))

    techs = [str(t).strip() for t in (lead.technologies or []) if str(t).strip()]
    techs = list(dict.fromkeys(techs))
    if techs:
        out.highlights.append(ProfileHighlight(
            highlight_title="Technology Focus", highlight_text=" • ".join(techs[:6]), trust_level=trust,
            supporting_signal_ids=signal_ids, supporting_source_ids=source_ids))

    signal_summary = build_signal_summary(lead)
    if signal_summary:
        out.highlights.append(ProfileHighlight(
            highlight_title="Hiring Signal", highlight_text=signal_summary, trust_level=trust,
            supporting_signal_ids=signal_ids, supporting_source_ids=source_ids))

    if opportunity and opportunity.label:
        out.highlights.append(ProfileHighlight(
            highlight_title="Potential Opportunity", highlight_text=opportunity.label,
            trust_level=trust, supporting_signal_ids=signal_ids, supporting_source_ids=source_ids))

    # --- AI insight (AI-authored, grounded, optional) ----------------------- #
    ai_generated = bool(ai_result and ai_result.ai_generated and _enum(ai_result.analysis_status)
                        in (AIAnalysisStatus.AI_VALIDATED.value, AIAnalysisStatus.AI_FLAGGED.value))
    if ai_generated:
        text = (ai_result.executive_summary or _first_supported_insight(ai_result) or "").strip()
        if text:
            out.ai_available = True
            out.ai_insight = text
            out.model_version = ai_result.model_name or ai_result.model_version
            out.generated_at = ai_result.generated_at.isoformat() if ai_result.generated_at else None
            out.highlights.append(ProfileHighlight(
                highlight_title="AI Insight", highlight_text=text, trust_level=trust,
                supporting_signal_ids=sorted({int(e) for e in ai_result.evidence_ids if isinstance(e, int)}),
                supporting_source_ids=[str(s) for s in (ai_result.source_ids or [])], ai_generated=True))
    if not out.ai_available:
        out.ai_insight = None          # UI renders _AI_UNAVAILABLE_TEXT; no fake prose
    return out


AI_UNAVAILABLE_TEXT = _AI_UNAVAILABLE_TEXT


def _enum(v) -> Optional[str]:
    return v.value if hasattr(v, "value") else v


def _first_supported_insight(ai_result: AIIntelligenceResult) -> Optional[str]:
    """Pick the first inferred insight that the validator did NOT flag unsupported."""
    for claim in (ai_result.inferred_insights or []):
        if isinstance(claim, dict) and claim.get("validation_status") != "UNSUPPORTED_CLAIM":
            text = (claim.get("claim_text") or "").strip()
            if text:
                return text
    return None
