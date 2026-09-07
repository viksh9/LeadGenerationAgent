"""Career source registry: declarative definitions of company career pages.

A `CareerSourceDefinition` holds NO credentials or personal data — just where a
public career page is, how to collect it, and its compliance posture. Loaded
from `config/career_sources.yaml`. Every entry starts PLANNED/disabled; a source
becomes CONNECTED only after real testing (§32).
"""

from __future__ import annotations

from enum import Enum
from functools import lru_cache
from pathlib import Path
from typing import Optional

import yaml
from pydantic import BaseModel, ConfigDict, Field

ROOT_DIR = Path(__file__).resolve().parent.parent.parent
DEFAULT_CAREER_SOURCES_PATH = ROOT_DIR / "config" / "career_sources.yaml"


class CollectionMethod(str, Enum):
    API = "API"
    RSS = "RSS"
    JSON = "JSON"
    PUBLIC_HTML = "PUBLIC_HTML"
    CAREER_PLATFORM = "CAREER_PLATFORM"


class RobotsStatus(str, Enum):
    ALLOWED = "ALLOWED"
    DISALLOWED = "DISALLOWED"
    UNKNOWN = "UNKNOWN"


class TermsStatus(str, Enum):
    ALLOWED = "ALLOWED"
    REQUIRES_REVIEW = "REQUIRES_REVIEW"
    RESTRICTED = "RESTRICTED"
    UNKNOWN = "UNKNOWN"


class CareerSourceStatus(str, Enum):
    PLANNED = "PLANNED"
    NOT_CONFIGURED = "NOT_CONFIGURED"
    REQUIRES_REVIEW = "REQUIRES_REVIEW"
    CONNECTED = "CONNECTED"
    RESTRICTED = "RESTRICTED"
    NOT_SUPPORTED = "NOT_SUPPORTED"
    ERROR = "ERROR"


class CareerSourceDefinition(BaseModel):
    """Declarative definition of one company's public career page."""

    model_config = ConfigDict(extra="forbid")

    source_id: str
    company_name: str
    company_domain: Optional[str] = None
    career_url: Optional[str] = None
    collection_method: CollectionMethod = CollectionMethod.PUBLIC_HTML
    parser_type: str = "generic"          # adapter/parser hint (§38)
    enabled: bool = False
    robots_status: RobotsStatus = RobotsStatus.UNKNOWN
    terms_status: TermsStatus = TermsStatus.UNKNOWN
    status: CareerSourceStatus = CareerSourceStatus.PLANNED
    country: Optional[str] = None
    industry: Optional[str] = None
    requires_js: bool = False             # (§37) JS-only pages are NOT_SUPPORTED
    requests_per_minute: Optional[int] = Field(default=None, ge=0)
    last_checked: Optional[str] = None    # ISO date string; informational only
    notes: Optional[str] = None

    @property
    def is_collectable(self) -> bool:
        """Whether automated collection is permitted for this source right now.

        Requires: enabled, a URL, robots not DISALLOWED, terms not RESTRICTED,
        and the page not JS-only. REQUIRES_REVIEW terms stay disabled unless the
        source itself is explicitly enabled for review (§21).
        """
        return (
            self.enabled
            and bool(self.career_url)
            and not self.requires_js
            and self.robots_status is not RobotsStatus.DISALLOWED
            and self.terms_status is not TermsStatus.RESTRICTED
        )


class CareerSourceRegistry:
    def __init__(self, sources: list[CareerSourceDefinition]) -> None:
        self._sources: dict[str, CareerSourceDefinition] = {}
        for src in sources:
            if src.source_id in self._sources:
                raise ValueError(f"duplicate career source_id: {src.source_id}")
            self._sources[src.source_id] = src

    def get(self, source_id: str) -> Optional[CareerSourceDefinition]:
        return self._sources.get(source_id)

    def all(self) -> list[CareerSourceDefinition]:
        return list(self._sources.values())

    def enabled(self) -> list[CareerSourceDefinition]:
        return [s for s in self._sources.values() if s.enabled]

    def __len__(self) -> int:
        return len(self._sources)


def load_career_sources(path: Path = DEFAULT_CAREER_SOURCES_PATH) -> list[CareerSourceDefinition]:
    """Load and validate career source definitions from YAML."""
    path = Path(path)
    if not path.exists():
        return []
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    raw = data.get("companies", data if isinstance(data, list) else [])
    return [CareerSourceDefinition(**entry) for entry in raw]


@lru_cache
def get_career_registry() -> CareerSourceRegistry:
    return CareerSourceRegistry(load_career_sources())
