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
from database.models import LeadPriority, SignalType
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
# Sales Pitch Generator
# ===========================================================================
#
# Deterministic, template-based, multi-channel B2B pitch generation. Consumes
# the analysis outputs (signals, opportunity, POC, score) and produces email /
# LinkedIn / call-talking-point messaging. No LLM, no network, no DB, no sending.
# Templates and message rules live in the tables below, separate from the core
# logic, so an LLM-based generator can be added later behind the same interface.


class MessageStrategy(str, Enum):
    HIRING_SUPPORT = "HIRING_SUPPORT"
    PROJECT_RAMP_UP = "PROJECT_RAMP_UP"
    SCALE_UP = "SCALE_UP"
    STAFF_AUGMENTATION = "STAFF_AUGMENTATION"
    VENDOR_ONBOARDING = "VENDOR_ONBOARDING"
    IMPLEMENTATION_DELIVERY = "IMPLEMENTATION_DELIVERY"
    TRANSFORMATION_DELIVERY = "TRANSFORMATION_DELIVERY"
    NURTURE = "NURTURE"


class ServiceAngle(str, Enum):
    STAFF_AUGMENTATION = "STAFF_AUGMENTATION"
    PROJECT_SUPPORT = "PROJECT_SUPPORT"
    ENGINEERING_CAPACITY = "ENGINEERING_CAPACITY"
    CLOUD_ENGINEERING = "CLOUD_ENGINEERING"
    SOFTWARE_DEVELOPMENT = "SOFTWARE_DEVELOPMENT"
    DEVOPS_SUPPORT = "DEVOPS_SUPPORT"
    DATA_ENGINEERING = "DATA_ENGINEERING"
    QA_AUTOMATION = "QA_AUTOMATION"
    TECHNOLOGY_IMPLEMENTATION = "TECHNOLOGY_IMPLEMENTATION"
    VENDOR_SUPPORT = "VENDOR_SUPPORT"


# Opportunity type value -> message strategy.
STRATEGY_BY_OPPORTUNITY: dict[str, MessageStrategy] = {
    "NORMAL_HIRING": MessageStrategy.HIRING_SUPPORT,
    "PROJECT_DRIVEN_HIRING": MessageStrategy.PROJECT_RAMP_UP,
    "LARGE_SCALE_RAMP_UP": MessageStrategy.SCALE_UP,
    "STAFF_AUGMENTATION": MessageStrategy.STAFF_AUGMENTATION,
    "VENDOR_OPPORTUNITY": MessageStrategy.VENDOR_ONBOARDING,
    "TECHNOLOGY_IMPLEMENTATION": MessageStrategy.IMPLEMENTATION_DELIVERY,
    "DIGITAL_TRANSFORMATION": MessageStrategy.TRANSFORMATION_DELIVERY,
    "LOW_CONFIDENCE": MessageStrategy.NURTURE,
}


@dataclass(frozen=True)
class _StrategyTemplate:
    subject: str          # {company} {tech}
    value_prop: str       # {company} {services}
    cta: str


# Message templates per strategy. Kept separate from the generation logic.
STRATEGY_TEMPLATES: dict[MessageStrategy, _StrategyTemplate] = {
    MessageStrategy.SCALE_UP: _StrategyTemplate(
        subject="Scaling your {tech} engineering team for the new project",
        value_prop="We help organizations scale engineering teams quickly with {services}, so delivery timelines hold as the team grows.",
        cta="Would you be open to a short discussion about your upcoming engineering capacity requirements?",
    ),
    MessageStrategy.PROJECT_RAMP_UP: _StrategyTemplate(
        subject="Engineering capacity for your project ramp-up",
        value_prop="We support project-driven teams with {services} that can be in place in weeks rather than months.",
        cta="Would it make sense to discuss the resource needs for your current project?",
    ),
    MessageStrategy.STAFF_AUGMENTATION: _StrategyTemplate(
        subject="Additional engineering capacity for your delivery team",
        value_prop="We provide flexible {services} that embeds into your existing delivery process and scales with each phase.",
        cta="Would you be open to a short discussion about your upcoming engineering capacity requirements?",
    ),
    MessageStrategy.VENDOR_ONBOARDING: _StrategyTemplate(
        subject="Technology delivery partnership for {company}",
        value_prop="We work with organizations as a technology delivery partner, offering {services} through a straightforward vendor onboarding path.",
        cta="Would it be useful to discuss your current technology vendor requirements and onboarding process?",
    ),
    MessageStrategy.IMPLEMENTATION_DELIVERY: _StrategyTemplate(
        subject="Delivery support for your technology implementation",
        value_prop="We help teams accelerate implementation and integration work with experienced {services}.",
        cta="Would a short technical discovery conversation be useful?",
    ),
    MessageStrategy.TRANSFORMATION_DELIVERY: _StrategyTemplate(
        subject="Engineering capacity for your transformation initiative",
        value_prop="Transformation programmes rely on sustained engineering capacity; we provide {services} that scales with each phase.",
        cta="Would a brief conversation about the engineering capacity for your transformation programme be useful?",
    ),
    MessageStrategy.HIRING_SUPPORT: _StrategyTemplate(
        subject="Supporting your engineering hiring",
        value_prop="We can supplement internal hiring with pre-vetted {services} when a search runs long or demand grows.",
        cta="Would a brief conversation be useful for when the need grows?",
    ),
    MessageStrategy.NURTURE: _StrategyTemplate(
        subject="Introduction — engineering delivery support for {company}",
        value_prop="We help teams add engineering capacity when projects or hiring ramp up. There is no specific ask today.",
        cta="Would it be helpful to understand whether you anticipate additional technology capacity needs in the near term?",
    ),
}

# Technology (lowercased) -> (human service phrase, service angle).
TECH_SERVICE_MAP: dict[str, tuple[str, ServiceAngle]] = {
    "java": ("backend engineering", ServiceAngle.SOFTWARE_DEVELOPMENT),
    "spring": ("backend engineering", ServiceAngle.SOFTWARE_DEVELOPMENT),
    "spring boot": ("backend engineering", ServiceAngle.SOFTWARE_DEVELOPMENT),
    ".net": ("backend engineering", ServiceAngle.SOFTWARE_DEVELOPMENT),
    "c#": ("backend engineering", ServiceAngle.SOFTWARE_DEVELOPMENT),
    "python": ("backend engineering", ServiceAngle.SOFTWARE_DEVELOPMENT),
    "node.js": ("backend engineering", ServiceAngle.SOFTWARE_DEVELOPMENT),
    "javascript": ("frontend engineering", ServiceAngle.SOFTWARE_DEVELOPMENT),
    "typescript": ("frontend engineering", ServiceAngle.SOFTWARE_DEVELOPMENT),
    "react": ("frontend engineering", ServiceAngle.SOFTWARE_DEVELOPMENT),
    "angular": ("frontend engineering", ServiceAngle.SOFTWARE_DEVELOPMENT),
    "aws": ("cloud engineering", ServiceAngle.CLOUD_ENGINEERING),
    "azure": ("cloud engineering", ServiceAngle.CLOUD_ENGINEERING),
    "gcp": ("cloud engineering", ServiceAngle.CLOUD_ENGINEERING),
    "kubernetes": ("platform engineering", ServiceAngle.DEVOPS_SUPPORT),
    "docker": ("platform engineering", ServiceAngle.DEVOPS_SUPPORT),
    "devops": ("DevOps", ServiceAngle.DEVOPS_SUPPORT),
    "kafka": ("data platform engineering", ServiceAngle.DATA_ENGINEERING),
    "data engineering": ("data platform engineering", ServiceAngle.DATA_ENGINEERING),
    "sql": ("data engineering", ServiceAngle.DATA_ENGINEERING),
    "mongodb": ("data engineering", ServiceAngle.DATA_ENGINEERING),
    "selenium": ("QA automation", ServiceAngle.QA_AUTOMATION),
    "playwright": ("QA automation", ServiceAngle.QA_AUTOMATION),
    "ai": ("AI/ML engineering", ServiceAngle.SOFTWARE_DEVELOPMENT),
    "ml": ("AI/ML engineering", ServiceAngle.SOFTWARE_DEVELOPMENT),
}

# Subtle industry wording (no regulatory/security claims).
INDUSTRY_PHRASE: dict[str, str] = {
    "IT": " We focus on engineering capacity and delivery scaling.",
    "BFSI": " We regularly support technology delivery and modernization programmes.",
    "HEALTHCARE": " We focus on technology delivery and platform modernization.",
    "FMCG": " We support digital platform and enterprise technology scaling.",
}


class PitchGenerationResult(BaseModel):
    """Multi-channel pitch output, ready for FastAPI / frontend / CRM / email."""

    model_config = ConfigDict(from_attributes=True)

    email_subject: str
    opening_message: str
    value_proposition: str
    recommended_pitch: str
    call_to_action: str
    linkedin_message: str
    call_talking_points: list[str] = Field(default_factory=list)
    target_role: Optional[str] = None
    message_strategy: MessageStrategy = MessageStrategy.NURTURE
    confidence: int = 0
    confidence_label: str = "LOW"


def _pget(source: Any, key: str, default: Any = None) -> Any:
    if source is None:
        return default
    if isinstance(source, Mapping):
        return source.get(key, default)
    return getattr(source, key, default)


def _normalize_industry_pitch(industry: Optional[str]) -> Optional[str]:
    if not industry:
        return None
    s = industry.lower()
    if any(k in s for k in ("bfsi", "bank", "financ", "insurance")):
        return "BFSI"
    if any(k in s for k in ("health", "pharma", "hospital", "clinic")):
        return "HEALTHCARE"
    if any(k in s for k in ("fmcg", "consumer goods", "cpg", "retail")):
        return "FMCG"
    if s == "it" or any(k in s for k in ("it services", "information technology", "software", "saas", "tech")):
        return "IT"
    return None


def _opp_value_pitch(opportunity: Any) -> Optional[str]:
    raw = _pget(opportunity, "opportunity_type")
    return getattr(raw, "value", raw)


def _extract_target_role(poc: Any, lead_data: Any) -> Optional[str]:
    # Works for POCFinder (primary_role.role) or POCEnricher (primary_contact.title).
    primary_role = _pget(poc, "primary_role")
    if primary_role is not None:
        role = _pget(primary_role, "role")
        if role:
            return role
    primary_contact = _pget(poc, "primary_contact")
    if primary_contact is not None:
        title = _pget(primary_contact, "title")
        if title:
            return title
    best = _pget(poc, "best_known_contact")
    if best is not None:
        title = _pget(best, "title")
        if title:
            return title
    return _pget(lead_data, "poc_title")


class PitchGenerator:
    """Deterministic, template-based multi-channel pitch generator."""

    def generate(
        self,
        lead_data: Any,
        signal_analysis: "SignalDetectionResult | dict | None" = None,
        opportunity_analysis: Any = None,
        poc_recommendation: Any = None,
        score_result: Any = None,
    ) -> PitchGenerationResult:
        if isinstance(signal_analysis, dict):
            signal_analysis = SignalDetectionResult(**signal_analysis)

        company = (_pget(lead_data, "company_name") or "your organization").strip()
        industry = _normalize_industry_pitch(_pget(lead_data, "industry"))
        techs = list(_pget(signal_analysis, "detected_technologies") or _pget(lead_data, "technologies") or [])
        hiring = _pget(signal_analysis, "estimated_hiring")
        if hiring is None:
            hiring = _pget(lead_data, "estimated_hiring")
        types = set(_pget(signal_analysis, "signal_types") or [])
        has_project = bool(types & {SignalType.PROJECT_AWARD, SignalType.PROJECT_EXECUTION, SignalType.CONTRACT})
        has_transformation = SignalType.DIGITAL_TRANSFORMATION in types
        has_hiring = SignalType.HIRING in types

        opp_value = _opp_value_pitch(opportunity_analysis) or "LOW_CONFIDENCE"
        strategy = STRATEGY_BY_OPPORTUNITY.get(opp_value, MessageStrategy.NURTURE)
        template = STRATEGY_TEMPLATES[strategy]

        tech_phrase = self._tech_phrase(techs)
        services = self._service_phrase(techs)
        target_role = _extract_target_role(poc_recommendation, lead_data)

        fmt = {"company": company, "tech": tech_phrase, "services": services}
        subject = template.subject.format(**fmt)
        opening = self._opening(strategy, company, tech_phrase, has_hiring, has_project, has_transformation, hiring)
        value_prop = template.value_prop.format(**fmt) + (INDUSTRY_PHRASE.get(industry, "") if industry else "")
        cta = template.cta
        recommended = f"{opening} {value_prop} {cta}"
        linkedin = self._linkedin(strategy, company, tech_phrase, services, cta)
        talking_points = self._talking_points(strategy, tech_phrase, has_project, has_hiring, bool(techs))
        confidence, label = self._confidence(
            signal_analysis, opportunity_analysis, score_result, company, techs, target_role
        )

        return PitchGenerationResult(
            email_subject=subject,
            opening_message=opening,
            value_proposition=value_prop.strip(),
            recommended_pitch=recommended.strip(),
            call_to_action=cta,
            linkedin_message=linkedin,
            call_talking_points=talking_points,
            target_role=target_role,
            message_strategy=strategy,
            confidence=confidence,
            confidence_label=label,
        )

    # -- helpers ------------------------------------------------------------

    @staticmethod
    def _tech_phrase(techs: list[str]) -> str:
        uniq = list(dict.fromkeys(techs))
        if not uniq:
            return "engineering"
        if len(uniq) == 1:
            return uniq[0]
        return f"{uniq[0]} and {uniq[1]}"

    @staticmethod
    def _service_phrase(techs: list[str]) -> str:
        phrases: list[str] = []
        for tech in techs:
            mapped = TECH_SERVICE_MAP.get(tech.lower())
            if mapped and mapped[0] not in phrases:
                phrases.append(mapped[0])
        if not phrases:
            return "engineering support"
        if len(phrases) == 1:
            return f"{phrases[0]} support"
        return f"{phrases[0]} and {phrases[1]} support"

    @staticmethod
    def _opening(
        strategy: MessageStrategy,
        company: str,
        tech_phrase: str,
        has_hiring: bool,
        has_project: bool,
        has_transformation: bool,
        hiring: Optional[int],
    ) -> str:
        if strategy is MessageStrategy.NURTURE:
            return (
                f"We came across some recent activity at {company} and wanted to introduce ourselves "
                f"as a potential engineering delivery partner."
            )
        observations: list[str] = []
        if has_hiring and tech_phrase != "engineering":
            observations.append(f"appears to be expanding its {tech_phrase} engineering capability")
        elif has_hiring:
            observations.append("appears to be expanding its engineering team")
        if has_project:
            observations.append("following a recent project award")
        if has_transformation:
            observations.append("as part of a digital transformation initiative")
        if not observations:
            observations.append(
                f"works with {tech_phrase} technologies" if tech_phrase != "engineering"
                else "may have upcoming technology initiatives"
            )
        opening = f"We noticed that {company} " + " ".join(observations) + "."
        # Only reference a hiring number when it is actually supplied.
        if hiring:
            opening += f" The activity suggests bringing on around {hiring} technology professionals."
        return opening

    @staticmethod
    def _linkedin(strategy: MessageStrategy, company: str, tech_phrase: str, services: str, cta: str) -> str:
        if strategy is MessageStrategy.NURTURE:
            body = (
                f"Hi, reaching out to introduce ourselves to the {company} team. "
                f"We help teams add flexible engineering capacity when projects or hiring ramp up. "
                f"Open to connecting for the future?"
            )
        else:
            observation = (
                f"is building {tech_phrase} engineering capability" if tech_phrase != "engineering"
                else "is scaling its engineering delivery"
            )
            body = (
                f"Hi, I noticed the {company} team {observation}. We help teams add flexible {services}. "
                f"Open to connecting and comparing notes on your upcoming resource needs?"
            )
        return body[:500]

    @staticmethod
    def _talking_points(
        strategy: MessageStrategy,
        tech_phrase: str,
        has_project: bool,
        has_hiring: bool,
        has_tech: bool,
    ) -> list[str]:
        points: list[str] = []
        if has_project:
            points.append("Ask about the current project delivery timeline and scope.")
        if has_hiring:
            points.append("Validate the expected engineering team size and roles.")
        if has_tech:
            points.append(f"Confirm {tech_phrase} resource requirements.")
        points.append("Understand whether internal hiring is sufficient for the expected ramp-up.")
        if strategy is MessageStrategy.VENDOR_ONBOARDING:
            points.append("Clarify the process for onboarding external technology vendors.")
        else:
            points.append("Explore how external engineering capacity could support delivery.")
        # Guarantee 3-5 points.
        while len(points) < 3:
            points.append("Understand the timeline for any upcoming technology capacity needs.")
        return points[:5]

    @staticmethod
    def _confidence(
        signal_analysis: Any,
        opportunity_analysis: Any,
        score_result: Any,
        company: str,
        techs: list[str],
        target_role: Optional[str],
    ) -> tuple[int, str]:
        strength = _pget(signal_analysis, "signal_strength", 0) or 0
        opp_conf = _pget(opportunity_analysis, "opportunity_confidence", 0) or 0
        score_conf = _pget(score_result, "scoring_confidence", 0) or 0
        conf = 20 if strength >= 50 else (10 if strength > 0 else 0)
        conf += round(opp_conf * 0.25)
        conf += round(score_conf * 0.15)
        if company and company != "your organization":
            conf += 10
        if techs:
            conf += 15
        if target_role:
            conf += 15
        conf = max(0, min(100, conf))
        if conf >= 80:
            label = "HIGH"
        elif conf >= 50:
            label = "MEDIUM"
        else:
            label = "LOW"
        return conf, label


def run_pitch_generation(
    lead_data: Any,
    signal_analysis: "SignalDetectionResult | dict | None" = None,
    opportunity_analysis: Any = None,
    poc_recommendation: Any = None,
    score_result: Any = None,
) -> PitchGenerationResult:
    """Convenience wrapper using a default-configured generator."""
    return PitchGenerator().generate(
        lead_data, signal_analysis, opportunity_analysis, poc_recommendation, score_result
    )
