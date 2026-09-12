"""Shared HTTP client for paid enrichment providers.

GET/POST JSON with a configurable auth header, per-provider rate limiting, and bounded
retry/backoff honouring Retry-After. Maps transport failures to the enrichment
exception types so a failure never becomes fabricated data. API keys are never logged.
"""

from __future__ import annotations

import logging
import time
from typing import Any, Callable, Optional

import httpx

from collectors.base import RateLimiter, RetryConfig, TimeoutConfig
from integrations.enrichment.base import (
    EnrichmentAuthError,
    EnrichmentBadResponse,
    EnrichmentForbidden,
    EnrichmentRateLimited,
    EnrichmentUnavailable,
)

logger = logging.getLogger("integrations.enrichment")
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)


class EnrichmentHttpClient:
    def __init__(self, *, base_url: str, auth_header: str, auth_value: str,
                 provider: str, requests_per_minute: int = 60, timeout_seconds: float = 20.0,
                 max_retries: int = 3, extra_headers: Optional[dict] = None,
                 http: httpx.Client | None = None, sleep: Callable[[float], None] = time.sleep,
                 limiter: RateLimiter | None = None) -> None:
        self.base_url = base_url.rstrip("/")
        self._headers = {auth_header: auth_value, "Accept": "application/json",
                         "Content-Type": "application/json", **(extra_headers or {})}
        self.provider = provider
        self.retry = RetryConfig(max_attempts=max(1, max_retries))
        self.timeout = TimeoutConfig(read_timeout=timeout_seconds)
        self._http = http
        self._sleep = sleep
        self._limiter = limiter or RateLimiter(requests_per_minute)

    def _client(self) -> httpx.Client:
        if self._http is not None:
            return self._http
        return httpx.Client(timeout=httpx.Timeout(self.timeout.read_timeout,
                                                  connect=self.timeout.connect_timeout))

    def request(self, method: str, path: str, *, params: Optional[dict] = None,
                json: Optional[dict] = None) -> Any:
        """Return parsed JSON, or None on 404. Raises the typed enrichment errors."""
        url = path if path.startswith("http") else f"{self.base_url}{path}"
        client = self._client()
        try:
            for attempt in range(1, self.retry.max_attempts + 1):
                if not self._limiter.allow():
                    self._sleep(1.0)
                logger.info("enrichment.provider_request provider=%s attempt=%s", self.provider, attempt)
                resp = client.request(method, url, headers=self._headers, params=params, json=json)
                status = resp.status_code
                if 200 <= status < 300:
                    try:
                        return resp.json()
                    except ValueError as exc:
                        raise EnrichmentBadResponse(f"{self.provider} returned non-JSON.") from exc
                if status == 404:
                    return None
                if status == 401:
                    raise EnrichmentAuthError(f"{self.provider} authentication failed (401).")
                if status == 403:
                    raise EnrichmentForbidden(f"{self.provider} forbidden (403).")
                if status == 429:
                    if attempt < self.retry.max_attempts:
                        self._sleep(self._retry_after(resp))
                        continue
                    logger.warning("enrichment.provider_rate_limited provider=%s", self.provider)
                    raise EnrichmentRateLimited(f"{self.provider} rate limited (429).")
                if attempt < self.retry.max_attempts and self.retry.is_retryable(status):
                    self._sleep(self.retry.backoff_for(attempt))
                    continue
                logger.warning("enrichment.provider_error provider=%s status_code=%s", self.provider, status)
                raise EnrichmentUnavailable(f"{self.provider} failed (HTTP {status}).")
            raise EnrichmentUnavailable(f"{self.provider} exhausted retries.")
        except (httpx.TimeoutException, httpx.HTTPError) as exc:
            logger.warning("enrichment.provider_error provider=%s reason=%s", self.provider, type(exc).__name__)
            raise EnrichmentUnavailable(f"{self.provider} request failed (network/timeout).") from exc
        finally:
            if self._http is None:
                client.close()

    def _retry_after(self, resp: httpx.Response) -> float:
        header = resp.headers.get("Retry-After", "")
        if header.isdigit():
            return min(float(header), self.retry.backoff_max_seconds)
        return self.retry.backoff_for(1)
