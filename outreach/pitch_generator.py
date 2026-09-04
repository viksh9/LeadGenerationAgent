"""Generate a concise outbound pitch from scored opportunity context."""

from dataclasses import dataclass

from config import get_settings
from intelligence.lead_scorer import LeadScore
from intelligence.opportunity_analyzer import OpportunityInsight


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
