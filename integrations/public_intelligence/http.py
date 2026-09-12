"""Shared public JSON HTTP client for free-source providers (GitHub, Wikidata).

GET-only, no secrets in logs, descriptive User-Agent (source etiquette), per-provider
rate limiting, and bounded retry/backoff honouring Retry-After. Maps transport
failures to the provider exception types so a failure never becomes fabricated data.
"""

from __future__ import annotations

import logging
import time
from typing import Any, Callable, Optional

import httpx

from collectors.base import RateLimiter, RetryConfig, TimeoutConfig
from integrations.public_intelligence.base import ProviderRateLimited, ProviderUnavailable

logger = logging.getLogger("integrations.public_intelligence")
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)


class PublicJsonClient:
    def __init__(self, *, base_url: str, user_agent: str, timeout_seconds: float = 20.0,
                 requests_per_minute: int = 30, headers: Optional[dict] = None,
                 max_retries: int = 3, backoff_cap_seconds: float = 30.0,
                 http: httpx.Client | None = None, sleep: Callable[[float], None] = time.sleep,
                 limiter: RateLimiter | None = None) -> None:
        self.base_url = base_url.rstrip("/")
        self._base_headers = {"User-Agent": user_agent, "Accept": "application/json", **(headers or {})}
        self.retry = RetryConfig(max_attempts=max(1, max_retries), backoff_max_seconds=backoff_cap_seconds)
        self.timeout = TimeoutConfig(read_timeout=timeout_seconds)
        self._http = http
        self._sleep = sleep
        self._limiter = limiter or RateLimiter(requests_per_minute)

    def _client(self) -> httpx.Client:
        if self._http is not None:
            return self._http
        return httpx.Client(timeout=httpx.Timeout(self.timeout.read_timeout,
                                                  connect=self.timeout.connect_timeout))

    def get_json(self, path: str, *, params: Optional[dict] = None,
                 provider: str = "public") -> Any:
        """GET a JSON resource. Returns parsed JSON, or None on 404. Raises
        ProviderRateLimited / ProviderUnavailable on throttling / transport failure."""
        url = path if path.startswith("http") else f"{self.base_url}{path}"
        client = self._client()
        try:
            for attempt in range(1, self.retry.max_attempts + 1):
                if not self._limiter.allow():
                    self._sleep(1.0)
                logger.info("public_intelligence.request provider=%s attempt=%s", provider, attempt)
                resp = client.get(url, params=params, headers=self._base_headers)
                status = resp.status_code
                if 200 <= status < 300:
                    try:
                        return resp.json()
                    except ValueError as exc:
                        raise ProviderUnavailable(f"{provider} returned non-JSON.") from exc
                if status == 404:
                    return None
                rate_limited = status == 429 or (
                    status == 403 and resp.headers.get("X-RateLimit-Remaining") == "0")
                if rate_limited:
                    if attempt < self.retry.max_attempts:
                        self._sleep(self._retry_after(resp))
                        continue
                    logger.warning("public_intelligence.rate_limited provider=%s", provider)
                    raise ProviderRateLimited(f"{provider} rate limited (HTTP {status}).")
                if attempt < self.retry.max_attempts and self.retry.is_retryable(status):
                    self._sleep(self.retry.backoff_for(attempt))
                    continue
                raise ProviderUnavailable(f"{provider} request failed (HTTP {status}).")
            raise ProviderUnavailable(f"{provider} exhausted retries.")
        except (httpx.TimeoutException, httpx.HTTPError) as exc:
            logger.warning("public_intelligence.error provider=%s reason=%s", provider, type(exc).__name__)
            raise ProviderUnavailable(f"{provider} request failed (network/timeout).") from exc
        finally:
            if self._http is None:
                client.close()

    def _retry_after(self, resp: httpx.Response) -> float:
        header = resp.headers.get("Retry-After", "")
        if header.isdigit():
            return min(float(header), self.retry.backoff_max_seconds)
        return self.retry.backoff_for(1)
