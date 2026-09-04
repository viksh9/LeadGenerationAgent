"""Classify and weight buying-intent signals from hiring, projects, and news."""

from dataclasses import dataclass
from datetime import datetime, timezone

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
