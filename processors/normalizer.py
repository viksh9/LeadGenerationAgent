"""Turn raw collector output into a consistent in-memory lead candidate."""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from collectors.base import RawCompanyRecord, RawSignal

VALID_SIGNAL_TYPES = {
    "hiring",
    "funding",
    "expansion",
    "tech_stack",
    "project",
    "leadership",
}


@dataclass
class NormalizedSignal:
    signal_type: str
    title: str
    description: str | None
    source: str | None
    source_url: str | None
    strength: float
    observed_at: datetime | None


@dataclass
class NormalizedLead:
    name: str
    domain: str | None
    industry: str | None
    size: str | None
    location: str | None
    description: str | None
    signals: list[NormalizedSignal]
    contacts: list[dict[str, Any]] = field(default_factory=list)


def _clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return max(low, min(high, value))


def normalize_signal(signal: RawSignal) -> NormalizedSignal | None:
    signal_type = (signal.signal_type or "").strip().lower().replace(" ", "_")
    if signal_type not in VALID_SIGNAL_TYPES:
        return None
    title = (signal.title or "").strip()
    if not title:
        return None
    return NormalizedSignal(
        signal_type=signal_type,
        title=title,
        description=(signal.description or "").strip() or None,
        source=signal.source,
        source_url=signal.source_url,
        strength=_clamp(float(signal.strength)),
        observed_at=signal.observed_at,
    )


def normalize_record(record: RawCompanyRecord) -> NormalizedLead | None:
    name = (record.name or "").strip()
    if not name:
        return None
    signals = [s for s in (normalize_signal(item) for item in record.signals) if s]
    return NormalizedLead(
        name=name,
        domain=(record.domain or "").strip() or None,
        industry=record.industry,
        size=record.size,
        location=record.location,
        description=record.description,
        signals=signals,
        contacts=list(record.contacts or []),
    )
