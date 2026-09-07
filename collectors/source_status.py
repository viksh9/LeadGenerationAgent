"""Truthful, runtime source connectivity status.

Reports each catalogued source's real state by combining its declared status
(``config/sources.yaml``) with whether its collector is implemented and whether
the credentials/configuration it needs are actually present in the environment.

Truthfulness rules (never overclaim):
  * A source is reported CONNECTED only after a real live health check has
    succeeded — never from configuration alone.
  * By default this module performs NO network calls; it reports configuration
    readiness only.
  * "Collector implemented" is tracked separately from "connected": having a
    collector class is not the same as an active real-data connection.

No LLM, no network (unless a caller explicitly opts into a live probe elsewhere).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

from collectors.source_registry import (
    SourceDefinition,
    SourceStatus,
    get_registry,
    source_api_key,
)


class RuntimeSourceStatus(str, Enum):
    """What the platform can honestly say about a source right now."""

    CONNECTED = "CONNECTED"                      # verified live (set only by a real probe)
    CONFIGURED = "CONFIGURED"                    # implemented + credentialed, not yet verified
    NOT_CONFIGURED = "NOT_CONFIGURED"            # implemented but missing credentials/config
    AUTHENTICATION_REQUIRED = "AUTHENTICATION_REQUIRED"
    REQUIRES_REVIEW = "REQUIRES_REVIEW"          # compliance/legal review pending
    PLANNED = "PLANNED"                          # catalogued, no collector yet
    DISABLED = "DISABLED"
    ERROR = "ERROR"


# Sources whose collectors are actually implemented in this codebase. Presence
# here means "a real collector exists" — NOT that it is connected.
_IMPLEMENTED_COLLECTORS: frozenset[str] = frozenset(
    {"adzuna", "jooble", "company_career_pages", "rss_news", "company_newsroom"}
)


@dataclass
class SourceStatusReport:
    source_id: str
    name: str
    category: str
    source_type: str
    collector_implemented: bool
    requires_api_key: bool
    status: RuntimeSourceStatus
    detail: str
    priority: int
    commercial_use_status: str
    provider: Optional[str] = None
    documentation_url: Optional[str] = None
    terms_url: Optional[str] = None
    authentication_type: str = "NONE"
    credential_env_vars: list[str] = field(default_factory=list)
    capabilities: list[str] = field(default_factory=list)
    supports_india: bool = False
    reliability_tier: Optional[str] = None


def _is_configured(defn: SourceDefinition) -> bool:
    """Whether the credentials/config this source needs are present in the env.

    Never returns True speculatively: for API sources it checks the actual env
    vars; for keyless sources that still need per-source config (feeds), it
    returns False until that config exists.
    """
    if defn.source_id == "adzuna":
        # Adzuna uses dedicated env vars (ADZUNA_APP_ID / ADZUNA_APP_KEY).
        from collectors.jobs.config import load_adzuna_config

        return load_adzuna_config().is_configured
    if defn.source_id == "jooble":
        from collectors.jobs.jooble import load_jooble_config

        return load_jooble_config().is_configured
    if defn.requires_api_key:
        return bool(source_api_key(defn.source_id))
    # Keyless collectors (career pages, RSS feeds) require reviewed per-source
    # config that is intentionally empty/disabled until vetted.
    return False


def source_runtime_status(defn: SourceDefinition) -> SourceStatusReport:
    """Compute a truthful runtime status for one source (no network)."""
    implemented = defn.source_id in _IMPLEMENTED_COLLECTORS

    if not defn.enabled and defn.status is SourceStatus.DISABLED:
        status, detail = RuntimeSourceStatus.DISABLED, "Source is disabled."
    elif defn.status is SourceStatus.PLANNED or not implemented:
        status = RuntimeSourceStatus.PLANNED
        detail = ("Catalogued but no collector is implemented yet."
                  if not implemented else "Planned; not yet available.")
    elif defn.status is SourceStatus.REQUIRES_REVIEW:
        status = RuntimeSourceStatus.REQUIRES_REVIEW
        detail = "Collector implemented; pending compliance/terms review before enabling."
    elif _is_configured(defn):
        status = RuntimeSourceStatus.CONFIGURED
        detail = ("Collector implemented and credentials configured. Not yet verified "
                  "against the live source — run a health check to confirm connectivity.")
    elif defn.requires_api_key:
        status = RuntimeSourceStatus.NOT_CONFIGURED
        detail = "Collector implemented but API credentials are not set in the environment."
    else:
        status = RuntimeSourceStatus.NOT_CONFIGURED
        detail = "Collector implemented but no reviewed per-source configuration is set."

    return SourceStatusReport(
        source_id=defn.source_id,
        name=defn.name,
        category=defn.category.value,
        source_type=defn.source_type.value,
        collector_implemented=implemented,
        requires_api_key=defn.requires_api_key,
        status=status,
        detail=detail,
        priority=defn.priority,
        commercial_use_status=defn.commercial_use_status.value,
        provider=defn.provider,
        documentation_url=defn.documentation_url,
        terms_url=defn.terms_url,
        authentication_type=defn.authentication_type.value,
        credential_env_vars=list(defn.credential_env_vars),
        capabilities=[c.value for c in defn.capabilities],
        supports_india=defn.supports_india,
        reliability_tier=defn.reliability_tier,
    )


def all_source_status(registry=None) -> list[SourceStatusReport]:
    """Runtime status for every catalogued source, highest priority first."""
    registry = registry or get_registry()
    reports = [source_runtime_status(defn) for defn in registry.all()]
    reports.sort(key=lambda r: (r.priority, r.name))
    return reports
