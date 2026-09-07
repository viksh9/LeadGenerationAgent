"""Source registry: declarative catalogue of the data sources we may collect from.

A `SourceDefinition` is pure configuration/metadata — it never holds credentials.
API keys are resolved at runtime from the environment (see `source_api_key`).
The registry is loaded from `config/sources.yaml`; every entry is PLANNED until
a real, tested collector exists for it.
"""

from __future__ import annotations

import os
from enum import Enum
from functools import lru_cache
from pathlib import Path
from typing import Optional

import yaml
from pydantic import BaseModel, ConfigDict, Field

ROOT_DIR = Path(__file__).resolve().parent.parent
DEFAULT_SOURCES_PATH = ROOT_DIR / "config" / "sources.yaml"


class SourceCategory(str, Enum):
    JOB = "JOB"
    COMPANY = "COMPANY"
    NEWS = "NEWS"
    PROJECT = "PROJECT"
    TENDER = "TENDER"
    GOVERNMENT = "GOVERNMENT"
    BUSINESS_DATABASE = "BUSINESS_DATABASE"
    OTHER = "OTHER"


class SourceType(str, Enum):
    API = "API"
    RSS = "RSS"
    PUBLIC_WEB = "PUBLIC_WEB"
    OPEN_DATA = "OPEN_DATA"
    THIRD_PARTY_API = "THIRD_PARTY_API"
    MANUAL_IMPORT = "MANUAL_IMPORT"


class SourceStatus(str, Enum):
    PLANNED = "PLANNED"
    AVAILABLE = "AVAILABLE"
    CONNECTED = "CONNECTED"
    DISABLED = "DISABLED"
    ERROR = "ERROR"


class ComplianceStatus(str, Enum):
    ALLOWED = "ALLOWED"
    RESTRICTED = "RESTRICTED"
    REQUIRES_APPROVAL = "REQUIRES_APPROVAL"
    UNKNOWN = "UNKNOWN"


class RateLimit(BaseModel):
    """Per-source polite request limits (respected by future collectors)."""

    requests_per_minute: Optional[int] = Field(default=None, ge=0)
    requests_per_day: Optional[int] = Field(default=None, ge=0)


class SourceCompliance(BaseModel):
    """Compliance posture for a source — documented, never bypassed."""

    terms_status: ComplianceStatus = ComplianceStatus.UNKNOWN
    robots_status: ComplianceStatus = ComplianceStatus.UNKNOWN
    api_terms_reviewed: bool = False
    commercial_use_status: ComplianceStatus = ComplianceStatus.UNKNOWN
    data_retention_notes: Optional[str] = None


class SourceDefinition(BaseModel):
    """Declarative definition of a collectable source. Contains NO secrets."""

    model_config = ConfigDict(extra="forbid")

    source_id: str
    name: str
    category: SourceCategory
    source_type: SourceType
    base_url: Optional[str] = None
    status: SourceStatus = SourceStatus.PLANNED
    enabled: bool = False
    requires_api_key: bool = False
    rate_limit: RateLimit = Field(default_factory=RateLimit)
    supports_search: bool = False
    supports_pagination: bool = False
    supports_incremental_fetch: bool = False
    supports_date_filter: bool = False
    data_quality: str = "UNKNOWN"
    commercial_use_status: ComplianceStatus = ComplianceStatus.UNKNOWN
    compliance: SourceCompliance = Field(default_factory=SourceCompliance)
    notes: Optional[str] = None

    @property
    def api_key_env_var(self) -> str:
        """Environment variable a real collector would read its key from."""
        return f"SOURCE_{self.source_id.upper()}_API_KEY"


def source_api_key(source_id: str) -> Optional[str]:
    """Resolve a source's API key from the environment (never stored/logged)."""
    return os.environ.get(f"SOURCE_{source_id.upper()}_API_KEY")


class SourceRegistry:
    """In-memory catalogue of source definitions, keyed by source_id."""

    def __init__(self, sources: list[SourceDefinition]) -> None:
        self._sources: dict[str, SourceDefinition] = {}
        for src in sources:
            if src.source_id in self._sources:
                raise ValueError(f"duplicate source_id in registry: {src.source_id}")
            self._sources[src.source_id] = src

    def get(self, source_id: str) -> Optional[SourceDefinition]:
        return self._sources.get(source_id)

    def all(self) -> list[SourceDefinition]:
        return list(self._sources.values())

    def list(
        self,
        *,
        category: Optional[SourceCategory] = None,
        status: Optional[SourceStatus] = None,
    ) -> list[SourceDefinition]:
        result = self.all()
        if category is not None:
            result = [s for s in result if s.category == category]
        if status is not None:
            result = [s for s in result if s.status == status]
        return result

    def __len__(self) -> int:
        return len(self._sources)


def load_sources(path: Path = DEFAULT_SOURCES_PATH) -> list[SourceDefinition]:
    """Load and validate source definitions from a YAML file."""
    data = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
    raw_sources = data.get("sources", data if isinstance(data, list) else [])
    return [SourceDefinition(**entry) for entry in raw_sources]


@lru_cache
def get_registry() -> SourceRegistry:
    """Cached registry loaded from the default YAML config."""
    return SourceRegistry(load_sources())
