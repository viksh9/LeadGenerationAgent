"""Collector contracts for inbound company and intent-signal records."""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass
class RawSignal:
    signal_type: str
    title: str
    description: str | None = None
    source: str | None = None
    source_url: str | None = None
    strength: float = 0.5
    observed_at: datetime | None = None
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass
class RawCompanyRecord:
    name: str
    domain: str | None = None
    industry: str | None = None
    size: str | None = None
    location: str | None = None
    description: str | None = None
    signals: list[RawSignal] = field(default_factory=list)
    contacts: list[dict[str, Any]] = field(default_factory=list)


class Collector(ABC):
    """Source adapter that yields company records with attached signals.

    Phase 1 uses local/offline sources only. Do not add HTTP scraping here.
    """

    name: str = "collector"

    @abstractmethod
    def collect(self) -> list[RawCompanyRecord]:
        raise NotImplementedError
