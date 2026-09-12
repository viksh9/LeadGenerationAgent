"""Pluggable ATS provider abstraction (Prompt 48 §7, §11).

Formalizes the existing ATS detection + collection behind a small provider
interface so new public ATS platforms can be added ONE AT A TIME when their public
interface is documented and permitted. Only Greenhouse and Lever are implemented
(both have documented public job-board/postings endpoints and are already wired
into the collector registry). Detection reuses the existing ``detect_ats`` logic —
this module does not reimplement parsing or fabricate board identifiers.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from collectors.base import BaseCollector
from collectors.company.career_source_discovery import detect_ats
from database.models import AtsProvider


class BaseATSProvider(ABC):
    """Contract for a public ATS integration."""

    provider: AtsProvider
    name: str

    @abstractmethod
    def detect(self, *, html: str, final_url: str) -> str | None:
        """Return the public board/site identifier if this ATS is detected, else None.
        Never fabricates an identifier."""

    @abstractmethod
    def build_collector(self, board_identifier: str) -> BaseCollector:
        """Build a collector for the detected public board (public postings only)."""


class GreenhouseATSProvider(BaseATSProvider):
    provider = AtsProvider.GREENHOUSE
    name = "Greenhouse"

    def detect(self, *, html: str, final_url: str) -> str | None:
        provider, board = detect_ats(html, final_url)
        return board if provider is AtsProvider.GREENHOUSE else None

    def build_collector(self, board_identifier: str) -> BaseCollector:
        from collectors.ats.greenhouse import GreenhouseCollector, GreenhouseConfig
        from collectors.source_registry import get_registry
        defn = get_registry().get("greenhouse")
        return GreenhouseCollector(defn, config=GreenhouseConfig(boards=[board_identifier]))


class LeverATSProvider(BaseATSProvider):
    provider = AtsProvider.LEVER
    name = "Lever"

    def detect(self, *, html: str, final_url: str) -> str | None:
        provider, board = detect_ats(html, final_url)
        return board if provider is AtsProvider.LEVER else None

    def build_collector(self, board_identifier: str) -> BaseCollector:
        from collectors.ats.lever import LeverCollector, LeverConfig
        from collectors.source_registry import get_registry
        defn = get_registry().get("lever")
        return LeverCollector(defn, config=LeverConfig(sites=[board_identifier]))


# Registry of IMPLEMENTED public ATS providers only (no planned/aspirational entries).
ATS_PROVIDERS: dict[AtsProvider, BaseATSProvider] = {
    AtsProvider.GREENHOUSE: GreenhouseATSProvider(),
    AtsProvider.LEVER: LeverATSProvider(),
}


def detect_ats_provider(*, html: str, final_url: str) -> tuple[BaseATSProvider | None, str | None]:
    """Detect which implemented ATS (if any) a page belongs to, plus its board id.
    Returns (None, None) when no supported public ATS is detected."""
    for provider in ATS_PROVIDERS.values():
        board = provider.detect(html=html, final_url=final_url)
        if board:
            return provider, board
    return None, None


def get_ats_provider(provider: AtsProvider) -> BaseATSProvider | None:
    return ATS_PROVIDERS.get(provider)


def supported_ats() -> list[str]:
    return [p.name for p in ATS_PROVIDERS.values()]
