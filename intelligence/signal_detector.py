"""Signal detection for LeadGenerationAgent.

Two APIs live here:

* ``SignalDetector`` (Phase 1) — a deterministic, configurable, dependency-light
  engine that turns raw lead text/fields into structured signal analysis. This
  is the component built for the current phase.
* ``detect_signals`` / ``DetectedSignal`` — the earlier buying-stage helper kept
  intact because other intelligence modules still import it; it will be
  superseded when scoring/opportunity are rebuilt.
"""

import re
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field

from database.models import SignalType
from processors.normalizer import NormalizedSignal

HIRING_KEYWORDS = (
    "engineer",
    "architect",
    "platform",
    "integration",
    "data",
    "operations systems",
    "product manager",
    "cto",
    "head of",
)
PROJECT_KEYWORDS = ("rfp", "implementation", "migration", "rollout", "automation", "replace")
FUNDING_KEYWORDS = ("series", "raised", "funding", "investment", "round")
EXPANSION_KEYWORDS = ("expand", "new market", "new office", "clinic", "warehouse", "store")
TECH_KEYWORDS = ("legacy", "migrate", "modernize", "api", "erp", "crm", "pos", "ehr")


@dataclass
class DetectedSignal:
    signal_type: str
    title: str
    description: str | None
    source: str | None
    source_url: str | None
    strength: float
    observed_at: datetime | None
    intent_tags: list[str]
    buying_stage: str


def _text(signal: NormalizedSignal) -> str:
    return f"{signal.title} {signal.description or ''}".lower()


def _tags_for(signal: NormalizedSignal) -> list[str]:
    blob = _text(signal)
    tags: list[str] = [signal.signal_type]
    keyword_map = {
        "hiring_buildout": HIRING_KEYWORDS,
        "active_project": PROJECT_KEYWORDS,
        "fresh_capital": FUNDING_KEYWORDS,
        "geographic_expansion": EXPANSION_KEYWORDS,
        "stack_change": TECH_KEYWORDS,
    }
    for tag, keywords in keyword_map.items():
        if any(keyword in blob for keyword in keywords):
            tags.append(tag)
    return list(dict.fromkeys(tags))


def _buying_stage(signal: NormalizedSignal, tags: list[str]) -> str:
    if signal.signal_type == "project":
        return "evaluation"
    if signal.signal_type == "funding":
        return "budgeted_growth"
    if signal.signal_type == "hiring":
        return "building_capacity"
    if signal.signal_type == "tech_stack":
        return "consideration"
    if signal.signal_type == "leadership":
        return "new_mandate"
    if signal.signal_type == "expansion":
        return "budgeted_growth"
    if "active_project" in tags:
        return "evaluation"
    return "awareness"


def _boost(signal: NormalizedSignal, tags: list[str]) -> float:
    boost = 0.0
    if "active_project" in tags:
        boost += 0.12
    if "fresh_capital" in tags:
        boost += 0.1
    if signal.signal_type == "hiring" and "hiring_buildout" in tags:
        boost += 0.08
    if signal.observed_at:
        observed = signal.observed_at
        if observed.tzinfo is None:
            observed = observed.replace(tzinfo=timezone.utc)
        age_days = (datetime.now(timezone.utc) - observed).days
        if age_days <= 30:
            boost += 0.08
        elif age_days <= 90:
            boost += 0.04
        elif age_days > 365:
            boost -= 0.1
    return boost


def detect_signals(signals: list[NormalizedSignal]) -> list[DetectedSignal]:
    detected: list[DetectedSignal] = []
    for signal in signals:
        tags = _tags_for(signal)
        strength = max(0.0, min(1.0, signal.strength + _boost(signal, tags)))
        detected.append(
            DetectedSignal(
                signal_type=signal.signal_type,
                title=signal.title,
                description=signal.description,
                source=signal.source,
                source_url=signal.source_url,
                strength=round(strength, 3),
                observed_at=signal.observed_at,
                intent_tags=tags,
                buying_stage=_buying_stage(signal, tags),
            )
        )
    return sorted(detected, key=lambda item: item.strength, reverse=True)


# ===========================================================================
# Phase 1 Signal Detection Engine
# ===========================================================================
#
# Deterministic, keyword/rule-based. No LLM, no network, no database access
# (the SignalType enum is reused from the DB layer only as a shared vocabulary).
# All detection rules live in the configuration structures below so they can be
# tuned or replaced without touching the detection logic.

STRONG = "STRONG"
MEDIUM = "MEDIUM"
WEAK = "WEAK"

# -- Signal keyword rules (configurable) ------------------------------------
# A single keyword may legitimately map to more than one signal type; that is
# intentional — a lead can carry multiple signals at once.
SIGNAL_KEYWORDS: dict[SignalType, tuple[str, ...]] = {
    SignalType.HIRING: (
        "hiring", "recruiting", "openings", "vacancies", "jobs", "engineers",
        "developers", "technical team", "technology hiring", "talent acquisition",
    ),
    SignalType.PROJECT_AWARD: (
        "awarded", "won contract", "contract awarded", "project awarded",
        "selected vendor", "deal won", "order received", "won", "bagged",
        "secured contract",
    ),
    SignalType.PROJECT_EXECUTION: (
        "implementation", "deployment", "rollout", "delivery",
        "project execution", "migration", "integration", "modernization",
    ),
    SignalType.EXPANSION: (
        "expansion", "new office", "new center", "new delivery center",
        "scaling team", "business expansion", "capacity expansion",
    ),
    SignalType.DIGITAL_TRANSFORMATION: (
        "digital transformation", "cloud migration", "cloud modernization",
        "digital modernization", "platform modernization",
        "technology transformation", "digitization", "modernization",
        "transformation",
    ),
    SignalType.TECHNOLOGY_INITIATIVE: (
        "ai initiative", "machine learning", "cloud initiative", "aws migration",
        "data platform", "automation initiative", "technology modernization",
    ),
    SignalType.VENDOR_REQUIREMENT: (
        "staff augmentation", "vendor requirement", "technology partner",
        "implementation partner", "development partner", "external resources",
        "contract resources", "outsourcing",
    ),
    SignalType.CONTRACT: (
        "contract", "agreement", "sow", "statement of work", "engagement",
        "master service agreement",
    ),
}

# -- Technology rules (configurable): canonical name -> match aliases --------
TECHNOLOGY_ALIASES: dict[str, tuple[str, ...]] = {
    "Java": ("java",),
    "Spring Boot": ("spring boot",),
    "Spring": ("spring",),
    "Python": ("python",),
    "JavaScript": ("javascript",),
    "TypeScript": ("typescript",),
    "React": ("react", "react.js", "reactjs"),
    "Angular": ("angular",),
    "Node.js": ("node.js", "nodejs", "node js"),
    ".NET": (".net", "dotnet"),
    "C#": ("c#",),
    "AWS": ("aws", "amazon web services"),
    "Azure": ("azure",),
    "GCP": ("gcp", "google cloud"),
    "Docker": ("docker",),
    "Kubernetes": ("kubernetes", "k8s"),
    "DevOps": ("devops",),
    "Kafka": ("kafka",),
    "Selenium": ("selenium",),
    "Playwright": ("playwright",),
    "AI": ("ai", "artificial intelligence"),
    "ML": ("ml", "machine learning"),
    "Data Engineering": ("data engineering",),
    "SQL": ("sql",),
    "MongoDB": ("mongodb", "mongo"),
}

# Suppress the less-specific tech when the more-specific one is present.
_TECH_SUPPRESS: dict[str, str] = {"Spring Boot": "Spring"}

# -- Source quality bonus (configurable) ------------------------------------
SOURCE_QUALITY: dict[str, int] = {
    "government tender": 8, "tender": 8, "press release": 6, "news": 5,
    "career page": 5, "careers": 5, "job portal": 4, "linkedin": 4,
    "company website": 3, "website": 3, "blog": 2,
}

# -- Reason templates (grounded only in matched keywords) -------------------
REASON_TEMPLATES: dict[SignalType, str] = {
    SignalType.HIRING: "The company is actively hiring technology professionals based on explicit hiring language ({keywords}).",
    SignalType.PROJECT_AWARD: "The company appears to have won a new project or contract based on project-award language ({keywords}).",
    SignalType.PROJECT_EXECUTION: "The company appears to be executing or delivering a project based on execution language ({keywords}).",
    SignalType.EXPANSION: "The company appears to be expanding operations or capacity based on expansion language ({keywords}).",
    SignalType.DIGITAL_TRANSFORMATION: "The initiative appears related to digital transformation based on modernization language ({keywords}).",
    SignalType.TECHNOLOGY_INITIATIVE: "The company appears to be pursuing a technology initiative based on the supplied text ({keywords}).",
    SignalType.VENDOR_REQUIREMENT: "The company appears to need external vendors or staff augmentation based on explicit language ({keywords}).",
    SignalType.CONTRACT: "A contractual engagement appears to be involved based on the supplied text ({keywords}).",
    SignalType.OTHER: "No strong opportunity signals were detected in the supplied text.",
}

# Number + optional descriptor + role noun, e.g. "30 Java engineers".
_HIRING_REGEX = re.compile(
    r"(\d+)\s+([A-Za-z0-9.#+/ ]*?)\b"
    r"(engineers?|developers?|specialists?|architects?|analysts?|"
    r"professionals?|resources?|testers?|consultants?)\b",
    re.IGNORECASE,
)


# -- Input / output models --------------------------------------------------


class SignalDetectionInput(BaseModel):
    """Raw information supplied to the detector (FastAPI/DB independent)."""

    signal_title: Optional[str] = None
    signal_description: Optional[str] = None
    technologies: list[str] = Field(default_factory=list)
    hiring_roles: list[str] = Field(default_factory=list)
    estimated_hiring: Optional[int] = None
    industry: Optional[str] = None
    project_name: Optional[str] = None
    project_value: Optional[float] = None
    source_name: Optional[str] = None


class DetectedSignalDetail(BaseModel):
    signal_type: SignalType
    detected_keywords: list[str] = Field(default_factory=list)
    reason: str


class SignalDetectionResult(BaseModel):
    """Structured analysis, ready for the Lead Analysis Pipeline / frontend."""

    model_config = ConfigDict(from_attributes=True)

    signal_types: list[SignalType] = Field(default_factory=list)
    signals: list[DetectedSignalDetail] = Field(default_factory=list)
    signal_strength: int = 0
    signal_strength_label: str = WEAK
    detected_keywords: list[str] = Field(default_factory=list)
    detected_technologies: list[str] = Field(default_factory=list)
    estimated_hiring: Optional[int] = None
    detected_roles: list[str] = Field(default_factory=list)
    project_value: Optional[float] = None
    reasons: list[str] = Field(default_factory=list)


@dataclass(frozen=True)
class DetectorConfig:
    """Bundle of detection rules; swap this to reconfigure the detector."""

    signal_keywords: Mapping[SignalType, tuple[str, ...]]
    technology_aliases: Mapping[str, tuple[str, ...]]
    source_quality: Mapping[str, int]
    reason_templates: Mapping[SignalType, str]


def default_config() -> DetectorConfig:
    return DetectorConfig(
        signal_keywords=SIGNAL_KEYWORDS,
        technology_aliases=TECHNOLOGY_ALIASES,
        source_quality=SOURCE_QUALITY,
        reason_templates=REASON_TEMPLATES,
    )


def _boundary_pattern(token: str) -> "re.Pattern[str]":
    """Case-insensitive, punctuation-tolerant whole-token/phrase matcher."""
    return re.compile(
        r"(?<![A-Za-z0-9])" + re.escape(token) + r"(?![A-Za-z0-9])",
        re.IGNORECASE,
    )


class SignalDetector:
    """Deterministic keyword/rule-based signal detector."""

    def __init__(self, config: Optional[DetectorConfig] = None) -> None:
        self.config = config or default_config()
        self._keyword_patterns: list[tuple[SignalType, str, "re.Pattern[str]"]] = [
            (stype, kw, _boundary_pattern(kw))
            for stype, keywords in self.config.signal_keywords.items()
            for kw in keywords
        ]
        self._tech_patterns: list[tuple[str, "re.Pattern[str]"]] = [
            (canonical, _boundary_pattern(alias))
            for canonical, aliases in self.config.technology_aliases.items()
            for alias in aliases
        ]

    # -- public API ---------------------------------------------------------

    def detect(
        self,
        data: "SignalDetectionInput | dict | None" = None,
        **fields,
    ) -> SignalDetectionResult:
        """Analyze raw lead information and return structured signals.

        Accepts a ``SignalDetectionInput``, a plain dict, or keyword fields.
        The original input is never mutated.
        """
        if data is None:
            data = SignalDetectionInput(**fields)
        elif isinstance(data, dict):
            data = SignalDetectionInput(**data)

        text = self._searchable_text(data)

        matches_by_type = self._match_signal_types(text)
        detected_technologies = self._detect_technologies(text, data.technologies)
        estimated_hiring, roles, hiring_phrases = self._detect_hiring(text, data)

        signal_types = list(matches_by_type.keys())
        signals: list[DetectedSignalDetail] = []
        reasons: list[str] = []
        detected_keywords: list[str] = []

        for stype in signal_types:
            kws = matches_by_type[stype]
            for kw in kws:
                if kw not in detected_keywords:
                    detected_keywords.append(kw)
            reason = self.config.reason_templates[stype].format(keywords=", ".join(kws))
            signals.append(DetectedSignalDetail(signal_type=stype, detected_keywords=kws, reason=reason))
            reasons.append(reason)

        for phrase in hiring_phrases:
            if phrase not in detected_keywords:
                detected_keywords.append(phrase)

        if not signal_types:
            reason = self.config.reason_templates[SignalType.OTHER]
            signal_types = [SignalType.OTHER]
            signals = [DetectedSignalDetail(signal_type=SignalType.OTHER, detected_keywords=[], reason=reason)]
            reasons = [reason]

        strength = self._strength(
            matches_by_type=matches_by_type,
            detected_technologies=detected_technologies,
            estimated_hiring=estimated_hiring,
            source_name=data.source_name,
        )

        return SignalDetectionResult(
            signal_types=signal_types,
            signals=signals,
            signal_strength=strength,
            signal_strength_label=self._label(strength),
            detected_keywords=detected_keywords,
            detected_technologies=detected_technologies,
            estimated_hiring=estimated_hiring,
            detected_roles=roles,
            project_value=data.project_value,
            reasons=reasons,
        )

    # -- internals ----------------------------------------------------------

    @staticmethod
    def _searchable_text(data: SignalDetectionInput) -> str:
        parts = [data.signal_title, data.signal_description, data.project_name, data.industry]
        joined = " ".join(p for p in parts if p)
        return re.sub(r"\s+", " ", joined).strip()

    def _match_signal_types(self, text: str) -> dict[SignalType, list[str]]:
        matches: dict[SignalType, list[str]] = {}
        if not text:
            return matches
        for stype, kw, pattern in self._keyword_patterns:
            if pattern.search(text):
                bucket = matches.setdefault(stype, [])
                if kw not in bucket:
                    bucket.append(kw)
        return matches

    def _detect_technologies(self, text: str, provided: list[str]) -> list[str]:
        found: list[str] = []
        for canonical, pattern in self._tech_patterns:
            if canonical not in found and text and pattern.search(text):
                found.append(canonical)
        for item in provided:
            canonical = self._canonical_tech(item) or (item.strip() or None)
            if canonical and canonical not in found:
                found.append(canonical)
        for specific, less_specific in _TECH_SUPPRESS.items():
            if specific in found and less_specific in found:
                found.remove(less_specific)
        return found

    def _canonical_tech(self, token: str) -> Optional[str]:
        needle = token.strip().lower()
        if not needle:
            return None
        for canonical, aliases in self.config.technology_aliases.items():
            if needle == canonical.lower() or needle in aliases:
                return canonical
        return None

    def _detect_hiring(
        self, text: str, data: SignalDetectionInput
    ) -> tuple[Optional[int], list[str], list[str]]:
        counts: list[int] = []
        roles: list[str] = []
        phrases: list[str] = []
        for match in _HIRING_REGEX.finditer(text):
            counts.append(int(match.group(1)))
            role = self._role_name(match.group(2).strip(), match.group(3))
            if role and role not in roles:
                roles.append(role)
            phrase = match.group(0).strip()
            if phrase not in phrases:
                phrases.append(phrase)

        estimated: Optional[int] = sum(counts) if counts else None
        if estimated is None and data.estimated_hiring is not None:
            estimated = data.estimated_hiring

        for role in data.hiring_roles:
            cleaned = role.strip()
            if cleaned and cleaned not in roles:
                roles.append(cleaned)
        return estimated, roles, phrases

    def _role_name(self, descriptor: str, noun: str) -> str:
        singular = noun[:-1] if noun.lower().endswith("s") else noun
        role_noun = singular.title()
        if not descriptor:
            return role_noun
        canonical = self._canonical_tech(descriptor)
        prefix = canonical if canonical else descriptor.title()
        return f"{prefix} {role_noun}".strip()

    def _strength(
        self,
        *,
        matches_by_type: dict[SignalType, list[str]],
        detected_technologies: list[str],
        estimated_hiring: Optional[int],
        source_name: Optional[str],
    ) -> int:
        real_types = [t for t in matches_by_type if t != SignalType.OTHER]
        if not real_types:
            return 0

        score = min(len(real_types), 4) * 12
        keyword_count = sum(len(v) for v in matches_by_type.values())
        score += min(keyword_count, 8) * 3
        if estimated_hiring:
            score += round(min(estimated_hiring, 40) / 40 * 18)
        score += min(len(detected_technologies), 6) * 3
        if SignalType.VENDOR_REQUIREMENT in real_types:
            score += 8
        if SignalType.PROJECT_AWARD in real_types:
            score += 6
        if SignalType.DIGITAL_TRANSFORMATION in real_types:
            score += 4
        score += self._source_bonus(source_name)
        return max(0, min(100, int(score)))

    def _source_bonus(self, source_name: Optional[str]) -> int:
        if not source_name:
            return 0
        needle = source_name.lower()
        bonuses = [bonus for key, bonus in self.config.source_quality.items() if key in needle]
        return max(bonuses) if bonuses else 0

    @staticmethod
    def _label(strength: int) -> str:
        if strength >= 80:
            return STRONG
        if strength >= 50:
            return MEDIUM
        return WEAK


def run_signal_detection(
    data: "SignalDetectionInput | dict | None" = None, **fields
) -> SignalDetectionResult:
    """Convenience wrapper using a default-configured detector."""
    return SignalDetector().detect(data, **fields)
