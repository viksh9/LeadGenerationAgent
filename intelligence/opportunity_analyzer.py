"""Deterministic opportunity analysis.

``OpportunityAnalyzer`` turns a ``SignalDetectionResult`` + lead data into an
IT-services/staffing opportunity assessment (type, staffing need, roles, team
size, urgency, confidence). No LLM, no network, no database.
"""

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field

from database.models import SignalType
from intelligence.signal_detector import SignalDetectionResult


# ===========================================================================
# Opportunity Analysis Engine
# ===========================================================================
#
# Deterministic. Consumes the SignalDetector's SignalDetectionResult (never
# re-detecting signals or technologies) plus the available lead data, and
# decides whether the signal looks like an IT-services / staffing / vendor
# opportunity. No LLM, no network, no database access (SignalType is reused
# from the DB layer only as a shared vocabulary).

from enum import Enum  # noqa: E402  (local to the engine section)


class OpportunityType(str, Enum):
    NORMAL_HIRING = "NORMAL_HIRING"
    PROJECT_DRIVEN_HIRING = "PROJECT_DRIVEN_HIRING"
    LARGE_SCALE_RAMP_UP = "LARGE_SCALE_RAMP_UP"
    STAFF_AUGMENTATION = "STAFF_AUGMENTATION"
    VENDOR_OPPORTUNITY = "VENDOR_OPPORTUNITY"
    TECHNOLOGY_IMPLEMENTATION = "TECHNOLOGY_IMPLEMENTATION"
    DIGITAL_TRANSFORMATION = "DIGITAL_TRANSFORMATION"
    LOW_CONFIDENCE = "LOW_CONFIDENCE"


class StaffingNeed(str, Enum):
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"
    UNKNOWN = "UNKNOWN"


class Urgency(str, Enum):
    CRITICAL = "CRITICAL"
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"
    UNKNOWN = "UNKNOWN"


# -- Configurable rule inputs ------------------------------------------------

# Canonical technology (as emitted by the SignalDetector) -> likely staffing
# roles. Only IT/engineering roles are produced; unrelated roles never appear.
ROLE_MAP: dict[str, tuple[str, ...]] = {
    "Java": ("Java Developer", "Java Engineer"),
    "Spring": ("Java Engineer",),
    "Spring Boot": ("Java Engineer",),
    "Python": ("Python Developer", "Backend Engineer"),
    "JavaScript": ("Frontend Engineer",),
    "TypeScript": ("Frontend Engineer",),
    "React": ("React Developer", "Frontend Engineer"),
    "Angular": ("Angular Developer", "Frontend Engineer"),
    "Node.js": ("Node.js Developer", "Backend Engineer"),
    ".NET": (".NET Developer",),
    "C#": (".NET Developer",),
    "AWS": ("AWS Engineer", "Cloud Engineer"),
    "Azure": ("Azure Engineer", "Cloud Engineer"),
    "GCP": ("Cloud Engineer",),
    "Docker": ("DevOps Engineer",),
    "Kubernetes": ("DevOps Engineer", "Platform Engineer"),
    "DevOps": ("DevOps Engineer",),
    "Kafka": ("Data Engineer",),
    "Selenium": ("QA Automation Engineer",),
    "Playwright": ("QA Automation Engineer",),
    "AI": ("AI Engineer", "ML Engineer"),
    "ML": ("ML Engineer", "AI Engineer"),
    "Data Engineering": ("Data Engineer",),
    "SQL": ("Database Engineer",),
    "MongoDB": ("Database Engineer",),
}

# Text cues (deterministic substring checks; matched case-insensitively).
STAFF_AUG_PHRASES: tuple[str, ...] = (
    "staff augmentation", "external resources", "contract resources",
    "contract staff", "augment the team", "additional engineers",
)
IMPL_PHRASES: tuple[str, ...] = (
    "implementation", "migration", "deployment", "rollout", "integration",
    "modernization", "go-live", "go live", "implement",
)
IMMEDIATE_PHRASES: tuple[str, ...] = (
    "immediately", "immediate", "urgent", "urgently", "asap", "right away",
)
RECENCY_PHRASES: tuple[str, ...] = (
    "last week", "recently", "this week", "this month", "this quarter",
    "just announced", "newly", "rapidly", "rapid",
)
DEADLINE_PHRASES: tuple[str, ...] = ("deadline", "by end of", "time-bound", "time bound")

SOURCE_CONFIDENCE_BONUS: dict[str, int] = {
    "government tender": 4, "tender": 4, "press release": 3, "news": 2,
    "careers": 2, "career page": 2, "linkedin": 1,
}

_HIGH_VALUE_SIGNALS = frozenset(
    {
        SignalType.PROJECT_AWARD,
        SignalType.VENDOR_REQUIREMENT,
        SignalType.PROJECT_EXECUTION,
        SignalType.DIGITAL_TRANSFORMATION,
        SignalType.TECHNOLOGY_INITIATIVE,
    }
)


@dataclass(frozen=True)
class OpportunityConfig:
    """Tunable thresholds for opportunity classification."""

    large_hiring_threshold: int = 20
    medium_hiring_threshold: int = 10
    confidence_high: int = 80
    confidence_medium: int = 50


def default_opportunity_config() -> OpportunityConfig:
    return OpportunityConfig()


class OpportunityAssessment(BaseModel):
    """Structured opportunity assessment, ready for the pipeline / frontend."""

    model_config = ConfigDict(from_attributes=True)

    opportunity_type: OpportunityType = OpportunityType.LOW_CONFIDENCE
    secondary_opportunity_types: list[OpportunityType] = Field(default_factory=list)
    potential_staffing_need: StaffingNeed = StaffingNeed.UNKNOWN
    likely_roles: list[str] = Field(default_factory=list)
    likely_technologies: list[str] = Field(default_factory=list)
    estimated_team_size_min: Optional[int] = None
    estimated_team_size_max: Optional[int] = None
    urgency: Urgency = Urgency.UNKNOWN
    business_reason: str = ""
    recommended_next_step: str = ""
    opportunity_confidence: int = 0
    opportunity_confidence_label: str = "LOW"


def _get(lead_data: Any, key: str, default: Any = None) -> Any:
    """Read a field from a dict or an object (duck-typed), without importing
    the API schema layer — keeps the analyzer FastAPI-independent."""
    if lead_data is None:
        return default
    if isinstance(lead_data, Mapping):
        return lead_data.get(key, default)
    return getattr(lead_data, key, default)


_OPP_SUMMARY: dict[OpportunityType, str] = {
    OpportunityType.LARGE_SCALE_RAMP_UP: "A large-scale, project-driven capacity ramp-up appears likely",
    OpportunityType.PROJECT_DRIVEN_HIRING: "Project-driven hiring appears to be underway",
    OpportunityType.STAFF_AUGMENTATION: "A staff-augmentation need appears likely",
    OpportunityType.VENDOR_OPPORTUNITY: "A vendor or delivery-partner opportunity appears likely",
    OpportunityType.TECHNOLOGY_IMPLEMENTATION: "A technology implementation opportunity appears likely",
    OpportunityType.DIGITAL_TRANSFORMATION: "A digital transformation opportunity appears likely",
    OpportunityType.NORMAL_HIRING: "This looks like routine hiring rather than a scaled staffing need",
}


class OpportunityAnalyzer:
    """Deterministic opportunity analysis built from small, readable rules."""

    def __init__(self, config: Optional[OpportunityConfig] = None) -> None:
        self.config = config or default_opportunity_config()

    # -- public API ---------------------------------------------------------

    def analyze(
        self,
        lead_data: Any,
        signal_analysis: "SignalDetectionResult | dict",
    ) -> OpportunityAssessment:
        if isinstance(signal_analysis, dict):
            signal_analysis = SignalDetectionResult(**signal_analysis)

        real = {t for t in signal_analysis.signal_types if t != SignalType.OTHER}
        hiring = self._hiring_volume(signal_analysis, lead_data)
        technologies = list(signal_analysis.detected_technologies)
        text = self._text(lead_data, signal_analysis)

        primary, secondary = self._opportunity_types(real, hiring, text)
        staffing = self._staffing_need(primary, hiring, technologies)
        team_min, team_max = self._team_size(signal_analysis, lead_data)
        roles = self._likely_roles(technologies, signal_analysis.detected_roles)
        urgency = self._urgency(real, hiring, text)
        confidence, label = self._confidence(signal_analysis, real, hiring, technologies, lead_data)

        return OpportunityAssessment(
            opportunity_type=primary,
            secondary_opportunity_types=secondary,
            potential_staffing_need=staffing,
            likely_roles=roles,
            likely_technologies=technologies,
            estimated_team_size_min=team_min,
            estimated_team_size_max=team_max,
            urgency=urgency,
            business_reason=self._business_reason(primary, hiring, technologies, real),
            recommended_next_step=self._next_step(primary, staffing),
            opportunity_confidence=confidence,
            opportunity_confidence_label=label,
        )

    # -- inputs -------------------------------------------------------------

    @staticmethod
    def _hiring_volume(sig: SignalDetectionResult, lead_data: Any) -> int:
        value = sig.estimated_hiring
        if value is None:
            value = _get(lead_data, "estimated_hiring")
        return value or 0

    @staticmethod
    def _text(lead_data: Any, sig: SignalDetectionResult) -> str:
        parts = [
            _get(lead_data, "signal_title"),
            _get(lead_data, "signal_description"),
            " ".join(sig.detected_keywords),
        ]
        return " ".join(p for p in parts if p).lower()

    # -- opportunity type ---------------------------------------------------

    def _opportunity_types(
        self, real: set, hiring: int, text: str
    ) -> tuple[OpportunityType, list[OpportunityType]]:
        S = SignalType
        large = hiring >= self.config.large_hiring_threshold
        staff_aug_lang = any(p in text for p in STAFF_AUG_PHRASES)
        impl_lang = (S.PROJECT_EXECUTION in real) or any(p in text for p in IMPL_PHRASES)

        candidates: list[OpportunityType] = []
        if S.HIRING in real and large:
            candidates.append(OpportunityType.LARGE_SCALE_RAMP_UP)
        if S.PROJECT_EXECUTION in real and staff_aug_lang:
            candidates.append(OpportunityType.STAFF_AUGMENTATION)
        if S.VENDOR_REQUIREMENT in real:
            candidates.append(OpportunityType.VENDOR_OPPORTUNITY)
        if S.PROJECT_AWARD in real and S.HIRING in real:
            candidates.append(OpportunityType.PROJECT_DRIVEN_HIRING)
        if S.TECHNOLOGY_INITIATIVE in real and impl_lang:
            candidates.append(OpportunityType.TECHNOLOGY_IMPLEMENTATION)
        if S.DIGITAL_TRANSFORMATION in real and S.HIRING in real:
            candidates.append(OpportunityType.DIGITAL_TRANSFORMATION)
        if S.HIRING in real and not large and not (real & _HIGH_VALUE_SIGNALS):
            candidates.append(OpportunityType.NORMAL_HIRING)

        if not candidates:  # gentle fallbacks before giving up
            if S.DIGITAL_TRANSFORMATION in real:
                candidates.append(OpportunityType.DIGITAL_TRANSFORMATION)
            elif S.TECHNOLOGY_INITIATIVE in real:
                candidates.append(OpportunityType.TECHNOLOGY_IMPLEMENTATION)
            elif S.HIRING in real:
                candidates.append(OpportunityType.NORMAL_HIRING)

        # De-duplicate, preserving priority order.
        ordered: list[OpportunityType] = []
        for opp in candidates:
            if opp not in ordered:
                ordered.append(opp)

        if not ordered:
            return OpportunityType.LOW_CONFIDENCE, []
        return ordered[0], ordered[1:]

    # -- staffing need ------------------------------------------------------

    def _staffing_need(
        self, primary: OpportunityType, hiring: int, technologies: list[str]
    ) -> StaffingNeed:
        cfg = self.config
        if primary is OpportunityType.LARGE_SCALE_RAMP_UP:
            return StaffingNeed.HIGH
        scaled = {
            OpportunityType.STAFF_AUGMENTATION,
            OpportunityType.VENDOR_OPPORTUNITY,
            OpportunityType.PROJECT_DRIVEN_HIRING,
            OpportunityType.DIGITAL_TRANSFORMATION,
            OpportunityType.TECHNOLOGY_IMPLEMENTATION,
        }
        if primary in scaled:
            if hiring >= cfg.large_hiring_threshold or (
                hiring >= cfg.medium_hiring_threshold and len(technologies) >= 2
            ):
                return StaffingNeed.HIGH
            return StaffingNeed.MEDIUM
        if primary in {OpportunityType.NORMAL_HIRING, OpportunityType.LOW_CONFIDENCE}:
            return StaffingNeed.LOW
        return StaffingNeed.UNKNOWN

    # -- team size ----------------------------------------------------------

    @staticmethod
    def _team_size(sig: SignalDetectionResult, lead_data: Any) -> tuple[Optional[int], Optional[int]]:
        # Only an explicit, extracted hiring count yields a range; vague
        # language returns null (never fabricate a precise number).
        explicit = sig.estimated_hiring
        if explicit is None:
            explicit = _get(lead_data, "estimated_hiring")
        if explicit and explicit > 0:
            return explicit, explicit
        return None, None

    # -- roles --------------------------------------------------------------

    @staticmethod
    def _likely_roles(technologies: list[str], detected_roles: list[str]) -> list[str]:
        roles: list[str] = []
        for tech in technologies:
            for role in ROLE_MAP.get(tech, ()):
                if role not in roles:
                    roles.append(role)
        for role in detected_roles:
            if role and role not in roles:
                roles.append(role)
        return roles

    # -- urgency ------------------------------------------------------------

    def _urgency(self, real: set, hiring: int, text: str) -> Urgency:
        if not real:
            return Urgency.UNKNOWN
        cfg = self.config
        score = 0
        if SignalType.PROJECT_AWARD in real:
            score += 2
        if hiring >= cfg.large_hiring_threshold:
            score += 2
        elif hiring >= cfg.medium_hiring_threshold:
            score += 1
        if any(p in text for p in IMMEDIATE_PHRASES):
            score += 2
        if any(p in text for p in RECENCY_PHRASES):
            score += 1
        if SignalType.PROJECT_EXECUTION in real:
            score += 1
        if any(p in text for p in DEADLINE_PHRASES):
            score += 1

        if score >= 5:
            return Urgency.CRITICAL
        if score >= 3:
            return Urgency.HIGH
        if score >= 1:
            return Urgency.MEDIUM
        return Urgency.LOW

    # -- confidence ---------------------------------------------------------

    def _confidence(
        self,
        sig: SignalDetectionResult,
        real: set,
        hiring: int,
        technologies: list[str],
        lead_data: Any,
    ) -> tuple[int, str]:
        score = sig.signal_strength * 0.5
        score += min(len(real), 3) * 6
        if real & {SignalType.PROJECT_AWARD, SignalType.PROJECT_EXECUTION}:
            score += 8
        if SignalType.HIRING in real and sig.estimated_hiring:
            score += 6
        if SignalType.VENDOR_REQUIREMENT in real:
            score += 6
        score += min(len(technologies), 4) * 2
        score += self._source_bonus(lead_data)

        value = max(0, min(100, int(round(score))))
        if value >= self.config.confidence_high:
            label = "HIGH"
        elif value >= self.config.confidence_medium:
            label = "MEDIUM"
        else:
            label = "LOW"
        return value, label

    @staticmethod
    def _source_bonus(lead_data: Any) -> int:
        source = _get(lead_data, "source_name")
        if not source:
            return 0
        needle = str(source).lower()
        bonuses = [b for key, b in SOURCE_CONFIDENCE_BONUS.items() if key in needle]
        return max(bonuses) if bonuses else 0

    # -- explanation + action ----------------------------------------------

    @staticmethod
    def _business_reason(
        primary: OpportunityType, hiring: int, technologies: list[str], real: set
    ) -> str:
        if primary is OpportunityType.LOW_CONFIDENCE:
            return "The available information does not clearly indicate an IT services or staffing opportunity."
        evidence: list[str] = []
        if SignalType.PROJECT_AWARD in real:
            evidence.append("a newly awarded project")
        if SignalType.PROJECT_EXECUTION in real:
            evidence.append("active project execution")
        if hiring:
            evidence.append(f"{hiring} technology openings")
        if SignalType.VENDOR_REQUIREMENT in real:
            evidence.append("explicit vendor/partner language")
        if SignalType.DIGITAL_TRANSFORMATION in real:
            evidence.append("a digital transformation initiative")
        clause = "; ".join(evidence) if evidence else "the detected signals"
        summary = _OPP_SUMMARY.get(primary, "An opportunity appears likely")
        tail = f", involving {', '.join(technologies[:5])}." if technologies else "."
        return f"{summary} based on {clause}{tail}"

    @staticmethod
    def _next_step(primary: OpportunityType, staffing: StaffingNeed) -> str:
        if primary is OpportunityType.VENDOR_OPPORTUNITY:
            return "Identify procurement/vendor-management and technology decision-makers."
        if primary in {
            OpportunityType.PROJECT_DRIVEN_HIRING,
            OpportunityType.LARGE_SCALE_RAMP_UP,
            OpportunityType.STAFF_AUGMENTATION,
            OpportunityType.TECHNOLOGY_IMPLEMENTATION,
        }:
            return "Identify project delivery and engineering leadership and validate resource requirements."
        if staffing is StaffingNeed.HIGH:
            return "Research the technology leadership team and prepare a staffing-focused outreach."
        if staffing is StaffingNeed.MEDIUM:
            return "Monitor hiring and project signals before outreach."
        return "Keep in nurture and monitor for stronger demand signals."


def run_opportunity_analysis(
    lead_data: Any,
    signal_analysis: "SignalDetectionResult | dict",
) -> OpportunityAssessment:
    """Convenience wrapper using a default-configured analyzer."""
    return OpportunityAnalyzer().analyze(lead_data, signal_analysis)
