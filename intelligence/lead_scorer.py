"""Lead scoring for LeadGenerationAgent.

Two APIs live here:

* ``LeadScorer`` (current) — a deterministic, explainable, configurable engine
  that scores a lead 0-100 across eight weighted categories and assigns a
  ``LeadPriority``. It consumes the detected signals + opportunity analysis +
  the lead's own fields. No LLM, no network, no database access, no FastAPI.
* ``score_lead`` / ``LeadScore`` — the earlier buying-stage scorer kept intact
  because other intelligence modules still import it.
"""

import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field

from database.models import LeadPriority, SignalType
from intelligence.signal_detector import DetectedSignal, SignalDetectionResult

TYPE_WEIGHTS = {
    "project": 28,
    "funding": 22,
    "hiring": 18,
    "leadership": 14,
    "expansion": 12,
    "tech_stack": 10,
}


@dataclass
class LeadScore:
    score: float
    intent_level: str
    reasons: list[str]


def _intent_level(score: float) -> str:
    if score >= 80:
        return "critical"
    if score >= 65:
        return "high"
    if score >= 40:
        return "medium"
    return "low"


def score_lead(signals: list[DetectedSignal]) -> LeadScore:
    if not signals:
        return LeadScore(score=0.0, intent_level="low", reasons=["No buying signals detected."])

    weighted = 0.0
    reasons: list[str] = []
    types_seen: set[str] = set()

    for signal in signals:
        weight = TYPE_WEIGHTS.get(signal.signal_type, 8)
        contribution = weight * signal.strength
        weighted += contribution
        types_seen.add(signal.signal_type)
        reasons.append(
            f"{signal.signal_type} ({signal.buying_stage}): {signal.title} "
            f"[strength {signal.strength:.2f}]"
        )

    diversity_bonus = max(0, len(types_seen) - 1) * 8
    high_strength = sum(1 for s in signals if s.strength >= 0.8)
    corroboration_bonus = 10 if high_strength >= 2 else 0

    raw = weighted + diversity_bonus + corroboration_bonus
    score = round(min(100.0, raw), 1)
    if diversity_bonus:
        reasons.append(f"Multiple signal categories ({len(types_seen)}) increased confidence.")
    if corroboration_bonus:
        reasons.append("Two or more high-strength signals corroborate intent.")
    return LeadScore(score=score, intent_level=_intent_level(score), reasons=reasons)


# ===========================================================================
# Lead Scoring Engine
# ===========================================================================
#
# Deterministic and explainable. Scores a lead across eight categories whose
# maximums sum to 100, so the breakdown always sums to the final score. Every
# category is capped at its configured maximum and can never go negative.
#
# Anti-double-counting is built into the category rules (see below), and all
# weights live in ``ScoringConfig`` — nothing is hard-coded across functions.

# Technologies relevant to the staff-augmentation / services capability. Kept
# lowercase for case-insensitive matching; configurable per offering.
_RELEVANT_TECHNOLOGIES = frozenset(
    {
        "java", "spring", "spring boot", "python", "javascript", "typescript",
        "react", "angular", "node.js", ".net", "c#", "aws", "azure", "gcp",
        "docker", "kubernetes", "devops", "kafka", "sql", "mongodb", "ai", "ml",
        "data engineering", "selenium", "playwright",
    }
)

_ENTERPRISE_INDUSTRIES = frozenset(
    {
        "bfsi", "bank", "insurance", "financial", "healthcare", "health",
        "telecom", "government", "public sector", "energy", "utilities", "pharma",
    }
)

_GOVERNMENT_KEYWORDS = (
    "government", "public sector", "public-sector", "ministry", "municipal",
    "federal", "state agency", "psu", "defense", "defence", "govt", "tender",
)


@dataclass(frozen=True)
class ScoringConfig:
    """All scoring weights, caps, and thresholds. Change here, not in the rules."""

    # Category maximums (sum == 100).
    large_hiring_max: int = 20
    project_award_max: int = 20
    enterprise_max: int = 15
    multiple_openings_max: int = 15
    expansion_max: int = 10
    technology_match_max: int = 10
    decision_maker_max: int = 5
    recency_max: int = 5

    # Project-evidence contributions (a single, strongest value is used).
    project_award_points: int = 20
    contract_points: int = 16
    project_execution_points: int = 12

    # Expansion / transformation contributions.
    digital_transformation_points: int = 8
    expansion_points: int = 6
    technology_initiative_points: int = 6

    # Technology match.
    relevant_technologies: frozenset = _RELEVANT_TECHNOLOGIES
    technology_points_per: float = 3.0

    # Enterprise / government indicators.
    enterprise_industries: frozenset = _ENTERPRISE_INDUSTRIES
    government_keywords: tuple = _GOVERNMENT_KEYWORDS
    enterprise_company_min: int = 1000
    enterprise_project_value: float = 1_000_000.0
    government_points: int = 8
    company_size_points: int = 5
    enterprise_industry_points: int = 5
    project_value_points: int = 5
    transformation_points: int = 3

    # Priority thresholds.
    hot_threshold: int = 80
    warm_threshold: int = 60
    nurture_threshold: int = 40


def default_scoring_config() -> ScoringConfig:
    return ScoringConfig()


class LeadScoreResult(BaseModel):
    """Structured scoring output, ready for the pipeline / FastAPI / frontend."""

    model_config = ConfigDict(from_attributes=True)

    score: int = 0
    priority: LeadPriority = LeadPriority.LOW
    score_breakdown: dict[str, int] = Field(default_factory=dict)
    positive_signals: list[str] = Field(default_factory=list)
    negative_signals: list[str] = Field(default_factory=list)
    explanation: str = ""
    scoring_confidence: int = 0
    scoring_confidence_label: str = "LOW"


def _get(source: Any, key: str, default: Any = None) -> Any:
    if source is None:
        return default
    if isinstance(source, dict):
        return source.get(key, default)
    return getattr(source, key, default)


_CATEGORY_PHRASES = {
    "large_technology_hiring": "significant technology hiring",
    "new_project_or_contract": "a recent project or contract award",
    "enterprise_project": "enterprise or government project indicators",
    "multiple_openings": "multiple relevant engineering roles",
    "expansion_or_transformation": "expansion or digital transformation activity",
    "technology_match": "a technology stack aligned with the service capability",
    "decision_maker": "an identifiable decision-maker",
    "recency": "a recent signal",
}


class LeadScorer:
    """Deterministic, explainable lead scoring across eight weighted categories."""

    def __init__(self, config: Optional[ScoringConfig] = None) -> None:
        self.config = config or default_scoring_config()

    def score(
        self,
        lead_data: Any,
        signal_analysis: "SignalDetectionResult | dict",
        opportunity_analysis: Any = None,
        *,
        now: Optional[datetime] = None,
    ) -> LeadScoreResult:
        """Score a lead. ``opportunity_analysis`` is optional corroboration.

        ``now`` may be injected for deterministic recency in tests; it defaults
        to the current UTC time.
        """
        if isinstance(signal_analysis, dict):
            signal_analysis = SignalDetectionResult(**signal_analysis)
        now = now or datetime.now(timezone.utc)

        types = {t for t in signal_analysis.signal_types if t != SignalType.OTHER}
        text = self._text(lead_data, signal_analysis)
        opp_type = getattr(getattr(opportunity_analysis, "opportunity_type", None), "value", None)

        breakdown = {
            "large_technology_hiring": self._score_hiring(signal_analysis, lead_data),
            "new_project_or_contract": self._score_project(types),
            "enterprise_project": self._score_enterprise(lead_data, text, opp_type),
            "multiple_openings": self._score_multiple_openings(signal_analysis),
            "expansion_or_transformation": self._score_expansion(types, opp_type),
            "technology_match": self._score_technology(signal_analysis.detected_technologies),
            "decision_maker": self._score_decision_maker(lead_data),
            "recency": self._score_recency(_get(lead_data, "signal_date"), now),
        }

        # Each category is capped at its maximum, so the sum is always in [0, 100]
        # and equals the final score by construction.
        score = max(0, min(100, sum(breakdown.values())))
        priority = self._priority(score)
        positive = self._positive_signals(breakdown, types)
        negative = self._negative_signals(breakdown)
        explanation = self._explanation(breakdown, score, priority)
        confidence, confidence_label = self._confidence(
            lead_data, signal_analysis, breakdown
        )

        return LeadScoreResult(
            score=score,
            priority=priority,
            score_breakdown=breakdown,
            positive_signals=positive,
            negative_signals=negative,
            explanation=explanation,
            scoring_confidence=confidence,
            scoring_confidence_label=confidence_label,
        )

    # -- inputs -------------------------------------------------------------

    @staticmethod
    def _text(lead_data: Any, signal: SignalDetectionResult) -> str:
        parts = [
            _get(lead_data, "signal_title"),
            _get(lead_data, "signal_description"),
            _get(lead_data, "source_name"),
            _get(lead_data, "industry"),
            " ".join(signal.detected_keywords),
        ]
        return " ".join(p for p in parts if p).lower()

    # -- A. Large technology hiring (max 20) --------------------------------

    def _score_hiring(self, signal: SignalDetectionResult, lead_data: Any) -> int:
        # Only use an explicitly extracted/provided count — never invent one.
        n = signal.estimated_hiring
        if n is None:
            n = _get(lead_data, "estimated_hiring")
        if not n or n <= 0:
            return 0
        if n >= 20:
            points = 16 + min(4, (n - 20) // 20 + 4)  # saturates quickly at 20
            points = 20
        elif n >= 10:
            points = 11 + round((n - 10) / 9 * 4)
        elif n >= 3:
            points = 6 + round((n - 3) / 6 * 4)
        else:
            points = round(n / 2 * 5)
        return min(points, self.config.large_hiring_max)

    # -- B. New project / contract (max 20) ---------------------------------

    def _score_project(self, types: set) -> int:
        # Anti-double-counting: take the single strongest project signal, not a
        # sum across PROJECT_AWARD + CONTRACT + PROJECT_EXECUTION.
        cfg = self.config
        candidates = []
        if SignalType.PROJECT_AWARD in types:
            candidates.append(cfg.project_award_points)
        if SignalType.CONTRACT in types:
            candidates.append(cfg.contract_points)
        if SignalType.PROJECT_EXECUTION in types:
            candidates.append(cfg.project_execution_points)
        if not candidates:
            return 0
        return min(max(candidates), cfg.project_award_max)

    # -- C. Enterprise / government project (max 15) ------------------------

    def _score_enterprise(self, lead_data: Any, text: str, opp_type: Optional[str]) -> int:
        cfg = self.config
        points = 0
        if any(k in text for k in cfg.government_keywords):
            points += cfg.government_points
        if self._is_large_company(_get(lead_data, "company_size")):
            points += cfg.company_size_points
        industry = (_get(lead_data, "industry") or "").lower()
        if industry and any(e in industry for e in cfg.enterprise_industries):
            points += cfg.enterprise_industry_points
        value = _get(lead_data, "project_value")
        if value and value >= cfg.enterprise_project_value:
            points += cfg.project_value_points
        if opp_type in {"DIGITAL_TRANSFORMATION", "LARGE_SCALE_RAMP_UP"}:
            points += cfg.transformation_points
        return min(points, cfg.enterprise_max)

    def _is_large_company(self, company_size: Optional[str]) -> bool:
        if not company_size:
            return False
        lowered = str(company_size).lower()
        if "enterprise" in lowered:
            return True
        numbers = [int(n) for n in re.findall(r"\d+", lowered)]
        return bool(numbers) and max(numbers) >= self.config.enterprise_company_min

    # -- D. Multiple relevant openings (max 15) -----------------------------

    def _score_multiple_openings(self, signal: SignalDetectionResult) -> int:
        # Breadth (distinct roles/technologies), NOT volume — that is category A.
        breadth = max(
            len(set(signal.detected_technologies)),
            len(set(signal.detected_roles)),
        )
        if breadth <= 0:
            points = 0
        elif breadth == 1:
            points = 3
        elif breadth == 2:
            points = 7
        elif breadth == 3:
            points = 11
        else:
            points = 15
        return min(points, self.config.multiple_openings_max)

    # -- E. Expansion / digital transformation (max 10) ---------------------

    def _score_expansion(self, types: set, opp_type: Optional[str]) -> int:
        cfg = self.config
        present = []
        if SignalType.DIGITAL_TRANSFORMATION in types:
            present.append(cfg.digital_transformation_points)
        if SignalType.EXPANSION in types:
            present.append(cfg.expansion_points)
        if SignalType.TECHNOLOGY_INITIATIVE in types:
            present.append(cfg.technology_initiative_points)
        if not present and opp_type == "DIGITAL_TRANSFORMATION":
            present.append(cfg.digital_transformation_points)
        if not present:
            return 0
        points = max(present) + (2 if len(present) > 1 else 0)
        return min(points, cfg.expansion_max)

    # -- F. Technology stack match (max 10) ---------------------------------

    def _score_technology(self, technologies: list) -> int:
        cfg = self.config
        matches = {t for t in technologies if t.lower() in cfg.relevant_technologies}
        points = round(len(matches) * cfg.technology_points_per)
        return min(points, cfg.technology_match_max)

    # -- G. Identifiable decision-maker (max 5) -----------------------------

    def _score_decision_maker(self, lead_data: Any) -> int:
        points = 0
        if _get(lead_data, "poc_name"):
            points += 2
        if _get(lead_data, "poc_title"):
            points += 2
        if _get(lead_data, "poc_linkedin_url") or _get(lead_data, "public_contact"):
            points += 1
        return min(points, self.config.decision_maker_max)

    # -- H. Recency (max 5) -------------------------------------------------

    def _score_recency(self, signal_date: Any, now: datetime) -> int:
        if not isinstance(signal_date, datetime):
            return 0
        if signal_date.tzinfo is None:
            signal_date = signal_date.replace(tzinfo=timezone.utc)
        days = (now - signal_date).days
        if days < 0:  # future dates are not evidence of recency
            return 0
        if days <= 7:
            return self.config.recency_max
        if days <= 30:
            return 4
        if days <= 90:
            return 2
        return 0

    # -- priority + narrative ----------------------------------------------

    def _priority(self, score: int) -> LeadPriority:
        cfg = self.config
        if score >= cfg.hot_threshold:
            return LeadPriority.HOT
        if score >= cfg.warm_threshold:
            return LeadPriority.WARM
        if score >= cfg.nurture_threshold:
            return LeadPriority.NURTURE
        return LeadPriority.LOW

    @staticmethod
    def _positive_signals(breakdown: dict[str, int], types: set) -> list[str]:
        pos: list[str] = []
        if breakdown["large_technology_hiring"] > 0:
            pos.append(
                "Large technology hiring detected"
                if breakdown["large_technology_hiring"] >= 11
                else "Technology hiring detected"
            )
        if breakdown["new_project_or_contract"] > 0:
            if SignalType.PROJECT_AWARD in types:
                pos.append("Recent project award detected")
            elif SignalType.CONTRACT in types:
                pos.append("Contract evidence detected")
            else:
                pos.append("Active project execution detected")
        if breakdown["enterprise_project"] > 0:
            pos.append("Enterprise or government project indicators detected")
        if breakdown["multiple_openings"] >= 6:
            pos.append("Multiple relevant engineering roles detected")
        if breakdown["expansion_or_transformation"] > 0:
            pos.append("Expansion or digital transformation detected")
        if breakdown["technology_match"] > 0:
            pos.append("Technology stack matches service capabilities")
        if breakdown["decision_maker"] > 0:
            pos.append("Identifiable decision-maker available")
        if breakdown["recency"] > 0:
            pos.append("Recent signal detected")
        return pos

    @staticmethod
    def _negative_signals(breakdown: dict[str, int]) -> list[str]:
        neg: list[str] = []
        if breakdown["large_technology_hiring"] == 0:
            neg.append("No reliable hiring volume available")
        elif breakdown["large_technology_hiring"] <= 5:
            neg.append("Only a small number of technology openings detected")
        if breakdown["new_project_or_contract"] == 0:
            neg.append("No project or contract evidence available")
        if breakdown["enterprise_project"] == 0:
            neg.append("No enterprise or government indicators available")
        if breakdown["multiple_openings"] <= 3:
            neg.append("Limited diversity of technology roles")
        if breakdown["technology_match"] == 0:
            neg.append("Technology stack does not match service capabilities")
        if breakdown["decision_maker"] == 0:
            neg.append("No identifiable decision-maker available")
        if breakdown["recency"] == 0:
            neg.append("No recent signal date available")
        return neg

    @staticmethod
    def _explanation(breakdown: dict[str, int], score: int, priority: LeadPriority) -> str:
        top = [k for k, v in sorted(breakdown.items(), key=lambda kv: kv[1], reverse=True) if v > 0][:3]
        if not top:
            return "The lead shows little evidence of an IT services or staffing opportunity."
        drivers = ", ".join(_CATEGORY_PHRASES[k] for k in top)
        return f"The lead scores {score}/100 ({priority.value}) primarily due to {drivers}."

    # -- scoring confidence -------------------------------------------------

    def _confidence(
        self, lead_data: Any, signal: SignalDetectionResult, breakdown: dict[str, int]
    ) -> tuple[int, str]:
        # How much *quality information* backs the score (not the score itself).
        conf = 0
        if _get(lead_data, "source_name"):
            conf += 15
        conf += 20 if signal.signal_strength >= 50 else (10 if signal.signal_strength > 0 else 0)
        if breakdown["new_project_or_contract"] > 0:
            conf += 20
        if breakdown["large_technology_hiring"] > 0:
            conf += 15
        if signal.detected_technologies:
            conf += 15
        if _get(lead_data, "signal_date") is not None:
            conf += 15
        conf = max(0, min(100, conf))
        if conf >= 80:
            label = "HIGH"
        elif conf >= 50:
            label = "MEDIUM"
        else:
            label = "LOW"
        return conf, label


def run_lead_scoring(
    lead_data: Any,
    signal_analysis: "SignalDetectionResult | dict",
    opportunity_analysis: Any = None,
    *,
    now: Optional[datetime] = None,
) -> LeadScoreResult:
    """Convenience wrapper using a default-configured scorer."""
    return LeadScorer().score(lead_data, signal_analysis, opportunity_analysis, now=now)
