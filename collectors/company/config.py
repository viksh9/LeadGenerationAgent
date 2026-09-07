"""Career-page collector configuration (env-driven, conservative defaults).

Global safety/policy knobs for the career-page framework. Per-source overrides
(URL, rate limit, robots/terms status, parser) live in the career source
registry (config/career_sources.yaml), not here.
"""

from __future__ import annotations

import os

from pydantic import BaseModel

# Transparent, non-deceptive user agent (§22). Configurable; never rotated to
# evade controls.
DEFAULT_USER_AGENT = "LeadGenerationAgent/0.1 (+contact@example.com)"

# Content types we are willing to parse (§49). Anything else is rejected.
ALLOWED_CONTENT_TYPES: tuple[str, ...] = (
    "text/html",
    "application/json",
    "application/ld+json",
    "application/rss+xml",
    "application/atom+xml",
    "application/xml",
    "text/xml",
)


class CareerCollectorConfig(BaseModel):
    user_agent: str = DEFAULT_USER_AGENT
    requests_per_minute: int = 10          # conservative default (§19)
    connect_timeout: float = 5.0
    read_timeout: float = 15.0
    max_pages: int = 3                     # pagination safety limit (§17, §45)
    max_records: int = 200                 # per-run record cap (§45)
    max_response_size_mb: float = 5.0      # (§47)
    max_redirects: int = 3                 # (§48)
    lookback_days: int = 30                # recency window (§18)
    # SSRF: private/loopback/link-local hosts are blocked unless explicitly
    # allowlisted for controlled testing (§46).
    allow_private_hosts: bool = False
    allowlisted_hosts: tuple[str, ...] = ()

    @property
    def max_response_bytes(self) -> int:
        return int(self.max_response_size_mb * 1024 * 1024)


def _env_int(key: str, default: int) -> int:
    try:
        return int(os.environ.get(key, default))
    except (TypeError, ValueError):
        return default


def _env_float(key: str, default: float) -> float:
    try:
        return float(os.environ.get(key, default))
    except (TypeError, ValueError):
        return default


def _env_list(key: str) -> tuple[str, ...]:
    value = os.environ.get(key)
    if not value:
        return ()
    return tuple(item.strip().lower() for item in value.split(",") if item.strip())


def load_career_config() -> CareerCollectorConfig:
    """Build the career-collector config from CAREER_* environment variables."""
    return CareerCollectorConfig(
        user_agent=os.environ.get("CAREER_USER_AGENT", DEFAULT_USER_AGENT),
        requests_per_minute=_env_int("CAREER_REQUESTS_PER_MINUTE", 10),
        connect_timeout=_env_float("CAREER_CONNECT_TIMEOUT", 5.0),
        read_timeout=_env_float("CAREER_READ_TIMEOUT", 15.0),
        max_pages=_env_int("CAREER_MAX_PAGES", 3),
        max_records=_env_int("CAREER_MAX_RECORDS", 200),
        max_response_size_mb=_env_float("CAREER_MAX_RESPONSE_SIZE_MB", 5.0),
        max_redirects=_env_int("CAREER_MAX_REDIRECTS", 3),
        lookback_days=_env_int("CAREER_LOOKBACK_DAYS", 30),
        allow_private_hosts=os.environ.get("CAREER_ALLOW_PRIVATE_HOSTS", "false").lower()
        in {"1", "true", "yes"},
        allowlisted_hosts=_env_list("CAREER_ALLOWLISTED_HOSTS"),
    )
