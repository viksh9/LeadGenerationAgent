"""Business collector config (reuses the generic safe-fetch config).

The safe HTTP client's config shape is generic; we reuse CareerCollectorConfig so
there is only one networking implementation. Business defaults favour feeds
(conservative rate, short lookback).
"""

from __future__ import annotations

import os

from collectors.company.config import DEFAULT_USER_AGENT, CareerCollectorConfig


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


def load_business_config() -> CareerCollectorConfig:
    """Safe-fetch config for business feeds from BUSINESS_* env vars."""
    return CareerCollectorConfig(
        user_agent=os.environ.get("BUSINESS_USER_AGENT", DEFAULT_USER_AGENT),
        requests_per_minute=_env_int("BUSINESS_REQUESTS_PER_MINUTE", 10),
        connect_timeout=_env_float("BUSINESS_CONNECT_TIMEOUT", 5.0),
        read_timeout=_env_float("BUSINESS_READ_TIMEOUT", 15.0),
        max_pages=_env_int("BUSINESS_MAX_PAGES", 3),
        max_records=_env_int("BUSINESS_MAX_RECORDS", 100),
        max_response_size_mb=_env_float("BUSINESS_MAX_RESPONSE_SIZE_MB", 5.0),
        max_redirects=_env_int("BUSINESS_MAX_REDIRECTS", 3),
        lookback_days=_env_int("BUSINESS_LOOKBACK_DAYS", 7),
        allow_private_hosts=os.environ.get("BUSINESS_ALLOW_PRIVATE_HOSTS", "false").lower()
        in {"1", "true", "yes"},
    )
