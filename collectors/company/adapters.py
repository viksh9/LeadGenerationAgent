"""Career-platform adapter architecture (extensible; most are stubs).

An adapter decides where to start collecting for a source and how to turn a
fetched page into jobs. Only `GenericCareerPageAdapter` is implemented. The ATS
adapters are interface stubs so future, separately-reviewed integrations have a
clear home — they make NO network calls and are marked unsupported.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Optional

from collectors.company.http_client import FetchedPage
from collectors.company.parsers import ParseResult, parse_jobs
from collectors.company.sources import CareerSourceDefinition


class CareerAdapter(ABC):
    name = "abstract"
    supported = False

    @abstractmethod
    def matches(self, source: CareerSourceDefinition) -> bool:
        """Whether this adapter handles the given source."""

    def start_url(self, source: CareerSourceDefinition) -> Optional[str]:
        return source.career_url

    @abstractmethod
    def parse(self, page: FetchedPage, source: CareerSourceDefinition) -> ParseResult:
        """Turn a fetched listing page into jobs + an optional next URL."""


class GenericCareerPageAdapter(CareerAdapter):
    """Structured-data-first adapter for arbitrary public career pages."""

    name = "generic"
    supported = True

    def matches(self, source: CareerSourceDefinition) -> bool:
        return True  # fallback for any source

    def parse(self, page: FetchedPage, source: CareerSourceDefinition) -> ParseResult:
        return parse_jobs(page.text, base_url=page.url)


class _UnsupportedAdapter(CareerAdapter):
    """Base for not-yet-implemented ATS adapters (no network calls)."""

    supported = False
    _hint = ""

    def matches(self, source: CareerSourceDefinition) -> bool:
        hint = self._hint
        return hint in (source.parser_type or "").lower() or hint in (source.company_domain or "").lower()

    def parse(self, page: FetchedPage, source: CareerSourceDefinition) -> ParseResult:  # pragma: no cover
        raise NotImplementedError(
            f"{self.name} adapter is not implemented yet; configure parser_type=generic "
            f"or wait for a reviewed {self.name} integration."
        )


class GreenhouseAdapter(_UnsupportedAdapter):
    name = "greenhouse"
    _hint = "greenhouse"


class LeverAdapter(_UnsupportedAdapter):
    name = "lever"
    _hint = "lever"


class WorkdayAdapter(_UnsupportedAdapter):
    name = "workday"
    _hint = "workday"


class SmartRecruitersAdapter(_UnsupportedAdapter):
    name = "smartrecruiters"
    _hint = "smartrecruiters"


# Specific adapters are consulted before the generic fallback.
_SPECIFIC_ADAPTERS: tuple[CareerAdapter, ...] = (
    GreenhouseAdapter(), LeverAdapter(), WorkdayAdapter(), SmartRecruitersAdapter(),
)


def select_adapter(source: CareerSourceDefinition) -> CareerAdapter:
    """Return the adapter for a source (specific match, else generic)."""
    for adapter in _SPECIFIC_ADAPTERS:
        if adapter.matches(source):
            return adapter
    return GenericCareerPageAdapter()
