"""Business-signal detection: classify text into a business signal + strength.

Deterministic, no-LLM. Reuses the technology detector; adds project-value and
date extraction. Claims are only made when the source text supports them — no
inferred project values, no assumed events.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

from config.business_signals import (
    BUSINESS_SIGNAL_KEYWORDS,
    IRRELEVANT_TERMS,
    STRONG_SIGNAL_TYPES,
    VALUE_MULTIPLIERS,
)
from database.models import BusinessSignalType, SignalStrength
from ingestion.extract import extract_technologies

_CURRENCY = {
    "₹": "INR", "rs": "INR", "rs.": "INR", "inr": "INR",
    "$": "USD", "us$": "USD", "usd": "USD",
    "€": "EUR", "eur": "EUR", "£": "GBP", "gbp": "GBP",
}
_VALUE_RE = re.compile(
    r"(₹|rs\.?|inr|us\$|usd|\$|€|eur|£|gbp)?\s*"
    r"([0-9][0-9,]*(?:\.[0-9]+)?)\s*"
    r"(crores?|cr|lakhs?|lac|billion|bn|million|mn|mil|thousand)?",
    re.IGNORECASE,
)


@dataclass
class BusinessSignalResult:
    signal_type: BusinessSignalType = BusinessSignalType.OTHER
    signal_strength: SignalStrength = SignalStrength.WEAK
    detected_keywords: list[str] = field(default_factory=list)
    reason: str = ""
    technologies: list[str] = field(default_factory=list)
    is_relevant: bool = False
    project_value: Optional[float] = None
    currency: Optional[str] = None
    project_value_text: Optional[str] = None


def extract_project_value(text: str) -> tuple[Optional[float], Optional[str], Optional[str]]:
    """Return (value, currency, original_text) only when explicitly stated.

    Requires a currency marker or a scale unit (crore/lakh/million/…), so plain
    counts ("500 engineers") are never treated as a project value."""
    if not text:
        return (None, None, None)
    best: tuple[float, Optional[str], str] | None = None
    for m in _VALUE_RE.finditer(text):
        cur_raw, num_raw, unit_raw = m.group(1), m.group(2), m.group(3)
        if not cur_raw and not unit_raw:
            continue  # bare number — not a value
        try:
            num = float(num_raw.replace(",", ""))
        except ValueError:
            continue
        mult = VALUE_MULTIPLIERS.get((unit_raw or "").lower(), 1.0)
        value = num * mult
        currency = _CURRENCY.get((cur_raw or "").lower().strip()) if cur_raw else None
        original = m.group(0).strip()
        if best is None or value > best[0]:
            best = (value, currency, original)
    if best is None:
        return (None, None, None)
    return best


def _classify(text: str) -> tuple[BusinessSignalType, list[str]]:
    for stype, keywords in BUSINESS_SIGNAL_KEYWORDS:
        hits = [k.strip() for k in keywords if k in text]
        if hits:
            return (stype, hits)
    return (BusinessSignalType.OTHER, [])


def _strength(stype: BusinessSignalType, technologies: list[str], has_value: bool, n_keywords: int) -> SignalStrength:
    if stype in STRONG_SIGNAL_TYPES and (has_value or technologies):
        return SignalStrength.STRONG
    if stype in STRONG_SIGNAL_TYPES or has_value:
        return SignalStrength.MEDIUM
    if stype is not BusinessSignalType.OTHER and technologies:
        return SignalStrength.MEDIUM
    if stype is not BusinessSignalType.OTHER:
        return SignalStrength.WEAK
    return SignalStrength.WEAK


class BusinessSignalDetector:
    def detect(self, title: Optional[str], description: Optional[str] = None) -> BusinessSignalResult:
        text = " ".join(p for p in (title, description) if p).lower()
        if not text.strip():
            return BusinessSignalResult(reason="empty text")
        stype, keywords = _classify(text)
        technologies = extract_technologies(text)
        value, currency, value_text = extract_project_value(text)
        strength = _strength(stype, technologies, value is not None, len(keywords))

        # Relevance: needs a business signal AND some IT evidence, and must not be
        # obvious non-IT noise without IT evidence.
        has_it = bool(technologies) or any(
            t in text for t in (
                "it services", "software", "technology", "engineering", "cloud", "digital",
                "cyber", "security", "data", " ai ", "ai ", "ml", "saas", "platform",
                "application", "api", "devops", "analytics", "fintech", "it ",
            )
        )
        noise = any(t in text for t in IRRELEVANT_TERMS)
        is_relevant = stype is not BusinessSignalType.OTHER and has_it and not (noise and not technologies)

        reason = (
            f"Detected {stype.value} from keywords ({', '.join(keywords)})."
            if keywords else "No explicit business-signal language detected."
        )
        return BusinessSignalResult(
            signal_type=stype, signal_strength=strength, detected_keywords=keywords,
            reason=reason, technologies=technologies, is_relevant=is_relevant,
            project_value=value, currency=currency, project_value_text=value_text,
        )


def signal_age_days(published_at: Optional[datetime], now: Optional[datetime] = None) -> Optional[int]:
    if published_at is None:
        return None
    now = now or datetime.now(timezone.utc).replace(tzinfo=None)
    pub = published_at.astimezone(timezone.utc).replace(tzinfo=None) if published_at.tzinfo else published_at
    ref = now.astimezone(timezone.utc).replace(tzinfo=None) if now.tzinfo else now
    return max(0, (ref - pub).days)
