"""Outbound pitch generation for LeadGenerationAgent.

Two APIs live here:

* ``PitchGenerator`` (current) — a deterministic, template-based engine that
  drafts a personalized outbound pitch from the analysis outputs (opportunity,
  signals, score, POC). No LLM, no network.
* ``generate_pitch`` / ``GeneratedPitch`` — the earlier helper (with an optional
  OpenAI path), kept intact because other modules/tests import it.
"""

from collections.abc import Mapping
from dataclasses import dataclass
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field

from config import get_settings
from database.models import LeadPriority
from enrichment.poc_finder import POCEnrichmentResult
from intelligence.lead_scorer import LeadScore, LeadScoreResult
from intelligence.opportunity_analyzer import (
    OpportunityAssessment,
    OpportunityInsight,
    OpportunityType,
    Urgency,
)
from intelligence.signal_detector import SignalDetectionResult


@dataclass
class GeneratedPitch:
    subject: str
    body: str
    angle: str


def _template_pitch(
    company_name: str,
    opportunity: OpportunityInsight,
    score: LeadScore,
    contact_name: str | None,
    contact_title: str | None,
) -> GeneratedPitch:
    greeting = f"Hi {contact_name.split()[0]}," if contact_name and " " in contact_name else "Hi,"
    role_note = f" As {contact_title}," if contact_title else ""
    pains = " ".join(opportunity.pain_hypotheses[:2])
    angle = opportunity.recommended_motion
    subject = f"Idea for {company_name}: {opportunity.primary_stage.replace('_', ' ')}"
    body = (
        f"{greeting}\n\n"
        f"{role_note} {opportunity.summary}\n\n"
        f"{pains}\n\n"
        f"Suggested next step: {angle}. "
        f"This account currently scores {score.score:.0f}/100 ({score.intent_level} intent).\n\n"
        "Happy to share a one-page brief tailored to the signals above."
    )
    return GeneratedPitch(subject=subject, body=body.strip(), angle=angle)


def _llm_pitch(
    company_name: str,
    opportunity: OpportunityInsight,
    score: LeadScore,
    contact_name: str | None,
    contact_title: str | None,
) -> GeneratedPitch | None:
    settings = get_settings()
    if not settings.openai_api_key:
        return None
    try:
        from openai import OpenAI
    except ImportError:
        return None

    client = OpenAI(api_key=settings.openai_api_key)
    prompt = (
        f"Write a short B2B outbound email (subject + body) to {contact_name or 'a decision maker'} "
        f"({contact_title or 'unknown title'}) at {company_name}. "
        f"Opportunity: {opportunity.summary} Motion: {opportunity.recommended_motion}. "
        f"Pains: {'; '.join(opportunity.pain_hypotheses)}. Score: {score.score}."
    )
    response = client.chat.completions.create(
        model=settings.openai_model,
        messages=[{"role": "user", "content": prompt}],
        temperature=0.4,
    )
    text = (response.choices[0].message.content or "").strip()
    if not text:
        return None
    lines = text.splitlines()
    subject = lines[0].replace("Subject:", "").strip()
    body = "\n".join(lines[1:]).strip() or text
    return GeneratedPitch(subject=subject[:255], body=body, angle=opportunity.recommended_motion)


def generate_pitch(
    company_name: str,
    opportunity: OpportunityInsight,
    score: LeadScore,
    contact_name: str | None = None,
    contact_title: str | None = None,
) -> GeneratedPitch:
    llm = _llm_pitch(company_name, opportunity, score, contact_name, contact_title)
    if llm:
        return llm
    return _template_pitch(company_name, opportunity, score, contact_name, contact_title)


# ===========================================================================
# Pitch Generation Engine
# ===========================================================================
#
# Deterministic and template-based. Turns the analysis outputs into a
# personalized outbound pitch. No LLM, no network, no database access.


class PitchTone(str, Enum):
    DIRECT = "DIRECT"
    CONSULTATIVE = "CONSULTATIVE"
    NURTURE = "NURTURE"


@dataclass(frozen=True)
class _PitchTemplate:
    angle: str
    subject: str  # format keys: {company} {tech} {team}
    opener: str
    points: tuple[str, ...]
    cta: str


# Configurable per-opportunity templates. Placeholders are filled deterministically.
PITCH_TEMPLATES: dict[OpportunityType, _PitchTemplate] = {
    OpportunityType.LARGE_SCALE_RAMP_UP: _PitchTemplate(
        angle="Project-driven capacity ramp-up",
        subject="Scaling {company}'s {tech} team for the new project",
        opener="Congratulations on the project win — standing up delivery capacity at short notice is usually the hardest part.",
        points=(
            "We can deploy vetted {tech} engineers to hit your ramp-up timeline.",
            "Flexible staff augmentation to add around {team} engineers without long hiring cycles.",
        ),
        cta="Would a short call this week to map your role-by-role needs be useful?",
    ),
    OpportunityType.PROJECT_DRIVEN_HIRING: _PitchTemplate(
        angle="Project-driven hiring support",
        subject="Helping {company} staff the new project quickly",
        opener="Noticed you are hiring alongside a new project — teams often need people faster than direct hiring allows.",
        points=(
            "Pre-vetted {tech} engineers, available in weeks rather than months.",
            "A blend of contract and contract-to-hire to de-risk the ramp.",
        ),
        cta="Open to a quick conversation about the roles you are prioritizing?",
    ),
    OpportunityType.STAFF_AUGMENTATION: _PitchTemplate(
        angle="Staff augmentation for active delivery",
        subject="Augmenting {company}'s delivery team with {tech} engineers",
        opener="With delivery in flight, adding capacity without disrupting the team is usually the priority.",
        points=(
            "Embedded {tech} engineers who plug into your existing process.",
            "Scale the team up or down as the project phases change.",
        ),
        cta="Happy to share profiles that match your current stack — worth a call?",
    ),
    OpportunityType.VENDOR_OPPORTUNITY: _PitchTemplate(
        angle="Delivery / technology partner",
        subject="A delivery partner for {company}'s technology initiative",
        opener="Saw signals that you are evaluating external partners for an upcoming initiative.",
        points=(
            "End-to-end delivery or targeted {tech} capacity, depending on your model.",
            "A straightforward path through procurement and vendor onboarding.",
        ),
        cta="Would it help to be included in your vendor evaluation?",
    ),
    OpportunityType.TECHNOLOGY_IMPLEMENTATION: _PitchTemplate(
        angle="Implementation delivery",
        subject="Delivery support for {company}'s {tech} implementation",
        opener="Implementations tend to stall on specialist capacity at exactly the wrong moment.",
        points=(
            "Experienced {tech} engineers to accelerate implementation and integration.",
            "Delivery-managed pods or individual specialists, whichever fits.",
        ),
        cta="Open to a short technical discovery call?",
    ),
    OpportunityType.DIGITAL_TRANSFORMATION: _PitchTemplate(
        angle="Digital transformation delivery",
        subject="Engineering capacity for {company}'s transformation programme",
        opener="Transformation programmes live or die on sustained engineering capacity.",
        points=(
            "Cloud and {tech} engineers to keep the programme moving.",
            "Flexible capacity that scales with each transformation phase.",
        ),
        cta="Would a call to walk through your roadmap and gaps be useful?",
    ),
    OpportunityType.NORMAL_HIRING: _PitchTemplate(
        angle="Targeted hiring support",
        subject="A hand with {company}'s current engineering hiring",
        opener="Saw you are hiring — happy to be a backstop if the search runs long.",
        points=(
            "Access to pre-vetted {tech} candidates when you need them.",
            "No obligation — a simple option to keep in your back pocket.",
        ),
        cta="Worth a brief intro call for when the need grows?",
    ),
    OpportunityType.LOW_CONFIDENCE: _PitchTemplate(
        angle="Introductory / nurture",
        subject="Introduction — engineering delivery for {company}",
        opener="Reaching out to introduce ourselves as a potential engineering delivery partner.",
        points=(
            "We help teams add engineering capacity when projects or hiring ramp up.",
            "No specific ask today — just opening the door for when the need arises.",
        ),
        cta="Open to staying in touch?",
    ),
}


class GeneratedPitchResult(BaseModel):
    """Deterministic, personalized outbound pitch."""

    model_config = ConfigDict(from_attributes=True)

    subject: str
    body: str
    angle: str
    tone: PitchTone = PitchTone.CONSULTATIVE
    talking_points: list[str] = Field(default_factory=list)
    call_to_action: str = ""
    target_persona: Optional[str] = None


def _get(source: Any, key: str, default: Any = None) -> Any:
    if source is None:
        return default
    if isinstance(source, Mapping):
        return source.get(key, default)
    return getattr(source, key, default)


class PitchGenerator:
    """Deterministic template-based pitch generation (no LLM, no network)."""

    def generate(
        self,
        lead_data: Any,
        opportunity: OpportunityAssessment,
        signal_analysis: Optional[SignalDetectionResult] = None,
        score: Optional[LeadScoreResult] = None,
        poc: Optional[POCEnrichmentResult] = None,
    ) -> GeneratedPitchResult:
        template = PITCH_TEMPLATES.get(
            opportunity.opportunity_type, PITCH_TEMPLATES[OpportunityType.LOW_CONFIDENCE]
        )
        company = (_get(lead_data, "company_name") or "your company").strip()
        technologies = list(getattr(signal_analysis, "detected_technologies", []) or [])
        tech_phrase = self._tech_phrase(technologies)
        team = getattr(signal_analysis, "estimated_hiring", None)
        team_phrase = str(team) if team else "additional"

        fmt = {"company": company, "tech": tech_phrase, "team": team_phrase}
        subject = template.subject.format(**fmt)
        points = [p.format(**fmt) for p in template.points]
        cta = template.cta.format(**fmt)

        greeting, persona = self._greeting(company, poc)
        tone = self._tone(opportunity, score)
        body = self._body(greeting, template.opener.format(**fmt), opportunity, points, cta)

        return GeneratedPitchResult(
            subject=subject,
            body=body,
            angle=template.angle,
            tone=tone,
            talking_points=points,
            call_to_action=cta,
            target_persona=persona,
        )

    # -- helpers ------------------------------------------------------------

    @staticmethod
    def _tech_phrase(technologies: list[str]) -> str:
        if not technologies:
            return "engineering"
        if len(technologies) == 1:
            return technologies[0]
        return f"{', '.join(technologies[:2])} and related"

    @staticmethod
    def _greeting(company: str, poc: Optional[POCEnrichmentResult]) -> tuple[str, Optional[str]]:
        best = getattr(poc, "best_known_contact", None) if poc else None
        if best and best.full_name:
            first = best.full_name.strip().split()[0]
            return f"Hi {first},", best.title
        primary = getattr(poc, "primary_contact", None) if poc else None
        if primary:
            return f"Hello {company} team,", primary.title
        return f"Hello {company} team,", None

    @staticmethod
    def _tone(opportunity: OpportunityAssessment, score: Optional[LeadScoreResult]) -> PitchTone:
        priority = getattr(score, "priority", None)
        if opportunity.urgency in {Urgency.CRITICAL, Urgency.HIGH} or priority is LeadPriority.HOT:
            return PitchTone.DIRECT
        if opportunity.opportunity_type is OpportunityType.LOW_CONFIDENCE or priority is LeadPriority.LOW:
            return PitchTone.NURTURE
        return PitchTone.CONSULTATIVE

    @staticmethod
    def _body(
        greeting: str,
        opener: str,
        opportunity: OpportunityAssessment,
        points: list[str],
        cta: str,
    ) -> str:
        bullets = "\n".join(f"- {p}" for p in points)
        context = opportunity.business_reason if opportunity.business_reason else ""
        sections = [greeting, opener]
        if context and opportunity.opportunity_type is not OpportunityType.LOW_CONFIDENCE:
            sections.append(context)
        sections.append(bullets)
        sections.append(cta)
        sections.append("Best regards,\nThe Delivery Team")
        return "\n\n".join(s for s in sections if s).strip()


def run_pitch_generation(
    lead_data: Any,
    opportunity: OpportunityAssessment,
    signal_analysis: Optional[SignalDetectionResult] = None,
    score: Optional[LeadScoreResult] = None,
    poc: Optional[POCEnrichmentResult] = None,
) -> GeneratedPitchResult:
    """Convenience wrapper using a default-configured generator."""
    return PitchGenerator().generate(lead_data, opportunity, signal_analysis, score, poc)
