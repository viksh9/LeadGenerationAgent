"""Score a prospect from corroborating intent signals."""

from dataclasses import dataclass

from intelligence.signal_detector import DetectedSignal

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
