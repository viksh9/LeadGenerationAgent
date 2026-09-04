"""Turn detected signals into a sales opportunity narrative and motion."""

from dataclasses import dataclass

from intelligence.signal_detector import DetectedSignal

STAGE_ORDER = [
    "evaluation",
    "budgeted_growth",
    "building_capacity",
    "new_mandate",
    "consideration",
    "awareness",
]

MOTION_BY_STAGE = {
    "evaluation": "RFP / solution workshop",
    "budgeted_growth": "Executive briefing on scale-up",
    "building_capacity": "Technical discovery with hiring manager",
    "new_mandate": "New-leader intro with 90-day plan",
    "consideration": "Problem-framing call",
    "awareness": "Nurture with insight content",
}


@dataclass
class OpportunityInsight:
    summary: str
    recommended_motion: str
    primary_stage: str
    pain_hypotheses: list[str]


def _primary_stage(signals: list[DetectedSignal]) -> str:
    if not signals:
        return "awareness"
    ranked = sorted(
        signals,
        key=lambda s: (STAGE_ORDER.index(s.buying_stage) if s.buying_stage in STAGE_ORDER else 99, -s.strength),
    )
    return ranked[0].buying_stage


def _pain_hypotheses(signals: list[DetectedSignal]) -> list[str]:
    hypotheses: list[str] = []
    blob = " ".join(f"{s.title} {s.description or ''}" for s in signals).lower()
    mapping = [
        ("spreadsheet", "Manual spreadsheet workflows are limiting operational visibility."),
        ("legacy", "Legacy systems are blocking integrations and slowing change."),
        ("rfp", "A formal buying process is already underway."),
        ("integrat", "Systems integration is a near-term delivery risk."),
        ("no-show", "Patient or customer no-shows are a measurable revenue leak."),
        ("warehouse", "Warehouse exceptions and inventory accuracy are executive priorities."),
        ("hiring", "New headcount implies a delivery gap the current stack cannot cover."),
    ]
    for needle, hypothesis in mapping:
        if needle in blob:
            hypotheses.append(hypothesis)
    if not hypotheses:
        hypotheses.append("Timing and stack change suggest an opening for a scoped pilot.")
    return list(dict.fromkeys(hypotheses))[:4]


def analyze_opportunity(company_name: str, signals: list[DetectedSignal]) -> OpportunityInsight:
    stage = _primary_stage(signals)
    if not signals:
        summary = f"{company_name} has no recent public intent signals."
    else:
        top = signals[0]
        extra = f" Corroborated by {len(signals)} signals." if len(signals) > 1 else ""
        summary = (
            f"{company_name} shows {stage.replace('_', ' ')} intent. "
            f"Strongest signal: {top.title}.{extra}"
        )
    return OpportunityInsight(
        summary=summary,
        recommended_motion=MOTION_BY_STAGE.get(stage, "Nurture with insight content"),
        primary_stage=stage,
        pain_hypotheses=_pain_hypotheses(signals),
    )
