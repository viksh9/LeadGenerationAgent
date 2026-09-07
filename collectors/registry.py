"""Collector registry — the single place that binds a source_id to its collector.

Only job sources that can be constructed from a source_id alone (their config
comes entirely from the environment) are registered here: Adzuna and Jooble.
Sources whose collectors need per-source configuration (career pages, RSS feeds)
are intentionally not source_id-runnable and are excluded.

"Registered" means a collector CLASS exists — NOT that the source is connected.
A source becomes CONNECTED only after a verified live request (see
collectors.connectivity).
"""

from __future__ import annotations

from typing import Callable

from collectors.base import BaseCollector
from collectors.errors import CollectorError
from collectors.source_registry import SourceDefinition, get_registry


class CollectorNotImplemented(CollectorError):
    """No collector is registered for the given source_id."""


def _build_adzuna(source: SourceDefinition) -> BaseCollector:
    from collectors.jobs.adzuna import AdzunaJobCollector

    return AdzunaJobCollector(source)


def _build_jooble(source: SourceDefinition) -> BaseCollector:
    from collectors.jobs.jooble import JoobleJobCollector

    return JoobleJobCollector(source)


# source_id -> factory(SourceDefinition) -> BaseCollector
COLLECTOR_FACTORIES: dict[str, Callable[[SourceDefinition], BaseCollector]] = {
    "adzuna": _build_adzuna,
    "jooble": _build_jooble,
}


def runnable_source_ids() -> frozenset[str]:
    """Source ids that can be run directly from the CLI/connectivity service."""
    return frozenset(COLLECTOR_FACTORIES)


def is_runnable(source_id: str) -> bool:
    return source_id in COLLECTOR_FACTORIES


def build_collector(source_id: str) -> BaseCollector:
    """Construct the collector for a source_id (config from the environment).

    Raises CollectorNotImplemented if no collector is registered, or CollectorError
    if the source_id is unknown to the catalogue.
    """
    factory = COLLECTOR_FACTORIES.get(source_id)
    if factory is None:
        raise CollectorNotImplemented(
            f"No runnable collector registered for source '{source_id}'. "
            f"Runnable sources: {sorted(runnable_source_ids())}."
        )
    source = get_registry().get(source_id)
    if source is None:
        raise CollectorError(f"Unknown source '{source_id}' (not in the source catalogue).")
    return factory(source)
