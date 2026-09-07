"""Low-level Adzuna HTTP client (network logic only; no mapping/business logic).

Respects the configured rate limit, timeouts, and a safe retry policy (transient
429/5xx only, honouring Retry-After). Credentials are sent as query params but
NEVER logged — logs use a redacted URL and credential-free params.
"""

from __future__ import annotations

import logging
import time
from typing import Any, Callable, Optional

import httpx

from collectors.base import RateLimiter, RetryConfig, TimeoutConfig
# Re-export the shared error taxonomy so existing
# `from collectors.jobs.client import CollectorError` imports keep working.
from collectors.errors import (  # noqa: F401
    CollectorError,
    SourceAuthError,
    SourceRateLimitError,
    SourceUnavailableError,
)
from collectors.jobs.config import AdzunaConfig

logger = logging.getLogger("collectors")

# httpx/httpcore echo the full (credential-bearing) URL in their logs — quiet them.
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)


class AdzunaClient:
    def __init__(
        self,
        config: AdzunaConfig,
        *,
        retry: RetryConfig | None = None,
        timeout: TimeoutConfig | None = None,
        http: httpx.Client | None = None,
        sleep: Callable[[float], None] = time.sleep,
        limiter: RateLimiter | None = None,
    ) -> None:
        self.config = config
        self.retry = retry or RetryConfig()
        self.timeout = timeout or TimeoutConfig(read_timeout=config.timeout_seconds)
        self._http = http
        self._sleep = sleep
        self._limiter = limiter or RateLimiter(config.requests_per_minute)

    def _client(self) -> httpx.Client:
        if self._http is not None:
            return self._http
        return httpx.Client(
            timeout=httpx.Timeout(self.timeout.read_timeout, connect=self.timeout.connect_timeout)
        )

    def search(self, *, country: str, page: int, params: dict[str, Any]) -> dict[str, Any]:
        """GET /jobs/{country}/search/{page} with credentials + params (creds never logged)."""
        url = f"{self.config.base_url}/jobs/{country}/search/{page}"
        redacted = f"{self.config.base_url}/jobs/{country}/search/{page}?***"
        full_params = {"app_id": self.config.app_id, "app_key": self.config.app_key, **params}
        client = self._client()
        try:
            for attempt in range(1, self.retry.max_attempts + 1):
                if not self._limiter.allow():
                    logger.info("rate_limit_wait source_id=adzuna")
                    self._sleep(1.0)
                logger.info("request_started source_id=adzuna url=%s page=%s attempt=%s", redacted, page, attempt)
                response = client.get(url, params=full_params)
                status = response.status_code
                if status == 200:
                    logger.info("request_completed source_id=adzuna page=%s status=200", page)
                    return response.json()
                # Credentials rejected — never retry, classify as auth failure.
                if status in (401, 403):
                    logger.error("collector_auth_failed source_id=adzuna status=%s", status)
                    raise SourceAuthError(f"Adzuna authentication failed (HTTP {status}).")
                if attempt < self.retry.max_attempts and (status == 429 or self.retry.is_retryable(status)):
                    wait = self._retry_after(response) if status == 429 else self.retry.backoff_for(attempt)
                    logger.warning("retry source_id=adzuna status=%s attempt=%s wait=%s", status, attempt, wait)
                    self._sleep(wait)
                    continue
                logger.error("collector_failed source_id=adzuna status=%s", status)
                if status == 429:
                    raise SourceRateLimitError("Adzuna rate limit exceeded (HTTP 429).")
                if self.retry.is_retryable(status):
                    raise SourceUnavailableError(f"Adzuna temporarily unavailable (HTTP {status}).")
                raise CollectorError(f"Adzuna request failed with HTTP {status}")
            raise SourceUnavailableError("Adzuna request exhausted retries.")
        finally:
            if self._http is None:
                client.close()

    def _retry_after(self, response: httpx.Response) -> float:
        header = response.headers.get("Retry-After", "")
        if header.isdigit():
            return min(float(header), self.retry.backoff_max_seconds)
        return self.retry.backoff_for(1)
