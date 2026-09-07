"""Adzuna collector configuration (from environment, with conservative defaults).

Credentials are read from the environment only — never hard-coded. The app
starts (and this config loads) even without credentials; `is_configured` is then
False and the collector reports NOT_CONFIGURED.
"""

from __future__ import annotations

import os
from typing import Optional

from pydantic import BaseModel

# Default IT-focused search terms (configurable via ADZUNA_SEARCH_TERMS).
DEFAULT_SEARCH_TERMS: tuple[str, ...] = (
    "Java developer", "Java engineer", "Python developer", "Python engineer",
    "software engineer", "software developer", "backend engineer", "frontend engineer",
    "full stack developer", "full stack engineer", "React developer", "Angular developer",
    "Node.js developer", ".NET developer", "AWS engineer", "Azure engineer", "cloud engineer",
    "DevOps engineer", "SRE", "platform engineer", "Kubernetes engineer", "data engineer",
    "data scientist", "machine learning engineer", "AI engineer", "QA automation engineer",
    "SDET", "test automation engineer", "automation tester", "technical lead",
    "engineering manager", "software architect", "solutions architect",
)

# Primary Indian IT hubs (configurable via ADZUNA_LOCATIONS).
DEFAULT_LOCATIONS: tuple[str, ...] = (
    "Bengaluru", "Hyderabad", "Pune", "Mumbai", "Chennai",
    "Delhi", "Noida", "Gurugram", "Kolkata", "Ahmedabad", "Remote",
)

# Lightweight IT-relevance terms (collection optimization only — the Signal
# Detection Engine remains the authority for business-signal classification).
IT_RELEVANCE_TERMS: tuple[str, ...] = (
    "software", "developer", "engineer", "cloud", "aws", "azure", "gcp", "devops",
    "java", "python", "javascript", "typescript", "react", "angular", "node",
    ".net", "c#", "kubernetes", "docker", "qa", "sdet", "automation", "data",
    "ai", "artificial intelligence", "machine learning", "ml", "technology",
    "technical", "backend", "frontend", "full stack", "sre", "platform", "architect",
)


class AdzunaConfig(BaseModel):
    base_url: str = "https://api.adzuna.com/v1/api"
    app_id: Optional[str] = None
    app_key: Optional[str] = None
    country: str = "in"
    search_terms: list[str] = list(DEFAULT_SEARCH_TERMS)
    locations: list[str] = list(DEFAULT_LOCATIONS)
    results_per_page: int = 20
    max_pages: int = 5
    lookback_days: int = 7
    requests_per_minute: int = 20
    daily_request_limit: int = 200
    timeout_seconds: float = 15.0

    @property
    def is_configured(self) -> bool:
        return bool(self.app_id and self.app_key and self.base_url)


def _env_list(key: str, default: tuple[str, ...]) -> list[str]:
    value = os.environ.get(key)
    if not value:
        return list(default)
    return [item.strip() for item in value.split(",") if item.strip()]


def _env_int(key: str, default: int) -> int:
    try:
        return int(os.environ.get(key, default))
    except (TypeError, ValueError):
        return default


def load_adzuna_config() -> AdzunaConfig:
    """Build the Adzuna config from environment variables."""
    return AdzunaConfig(
        base_url=os.environ.get("ADZUNA_API_BASE_URL", "https://api.adzuna.com/v1/api"),
        app_id=os.environ.get("ADZUNA_APP_ID") or None,
        app_key=os.environ.get("ADZUNA_APP_KEY") or None,
        country=os.environ.get("ADZUNA_COUNTRY", "in"),
        search_terms=_env_list("ADZUNA_SEARCH_TERMS", DEFAULT_SEARCH_TERMS),
        locations=_env_list("ADZUNA_LOCATIONS", DEFAULT_LOCATIONS),
        results_per_page=_env_int("ADZUNA_RESULTS_PER_PAGE", 20),
        max_pages=_env_int("ADZUNA_MAX_PAGES", 5),
        lookback_days=_env_int("ADZUNA_LOOKBACK_DAYS", 7),
        requests_per_minute=_env_int("ADZUNA_REQUESTS_PER_MINUTE", 20),
        daily_request_limit=_env_int("ADZUNA_DAILY_REQUEST_LIMIT", 200),
        timeout_seconds=float(os.environ.get("ADZUNA_TIMEOUT_SECONDS", 15)),
    )
