"""Safe HTTP client for public career pages.

Enforces the collector's safety controls on every request: scheme/SSRF
validation, a bounded number of validated redirects, a max response size, a
content-type allowlist, a polite rate limit, and transient-only retries. Sends
only a transparent User-Agent + Accept — never cookies, auth, or credentials.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Callable, Optional
from urllib.parse import urljoin, urlsplit

import httpx

from collectors.base import RateLimiter, RetryConfig, TimeoutConfig
from collectors.company.config import ALLOWED_CONTENT_TYPES, CareerCollectorConfig
from collectors.company.safety import SafetyError, validate_public_url

logger = logging.getLogger("collectors")

# httpx/httpcore can echo full URLs (and any query) in their logs — quiet them.
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)

_REDIRECT_CODES = (301, 302, 303, 307, 308)


class CareerCollectorError(RuntimeError):
    """Unrecoverable career-collector failure (safety, config, or HTTP)."""


class RestrictedError(CareerCollectorError):
    """Access is restricted (e.g. repeated 403) — the source is not collectable."""


@dataclass
class FetchedPage:
    url: str
    status: int
    content_type: str
    text: str
    elapsed_seconds: float


class SafeHttpClient:
    def __init__(
        self,
        config: CareerCollectorConfig,
        *,
        retry: RetryConfig | None = None,
        timeout: TimeoutConfig | None = None,
        http: httpx.Client | None = None,
        sleep: Callable[[float], None] = time.sleep,
        limiter: RateLimiter | None = None,
        resolve_hosts: bool = False,
    ) -> None:
        self.config = config
        self.retry = retry or RetryConfig()
        self.timeout = timeout or TimeoutConfig(
            connect_timeout=config.connect_timeout, read_timeout=config.read_timeout
        )
        self._http = http
        self._sleep = sleep
        self._limiter = limiter or RateLimiter(config.requests_per_minute)
        self._resolve = resolve_hosts

    # -- validation --------------------------------------------------------- #
    def _validate(self, url: str) -> str:
        return validate_public_url(
            url,
            resolve=self._resolve,
            allow_private=self.config.allow_private_hosts,
            allowlisted_hosts=self.config.allowlisted_hosts,
        )

    def _headers(self) -> dict[str, str]:
        return {
            "User-Agent": self.config.user_agent,
            "Accept": "text/html,application/xhtml+xml,application/json,application/ld+json;q=0.9,*/*;q=0.5",
        }

    def _client(self) -> httpx.Client:
        if self._http is not None:
            return self._http
        return httpx.Client(
            timeout=httpx.Timeout(self.timeout.read_timeout, connect=self.timeout.connect_timeout),
            follow_redirects=False,
        )

    # -- reading ------------------------------------------------------------ #
    def _read_capped(self, response: httpx.Response) -> str:
        limit = self.config.max_response_bytes
        cl = response.headers.get("content-length")
        if cl and cl.isdigit() and int(cl) > limit:
            raise CareerCollectorError(f"response too large (Content-Length {cl} > {limit})")
        total = 0
        chunks: list[bytes] = []
        for chunk in response.iter_bytes():
            total += len(chunk)
            if total > limit:
                raise CareerCollectorError(f"response exceeded max size ({limit} bytes)")
            chunks.append(chunk)
        return b"".join(chunks).decode(response.encoding or "utf-8", errors="replace")

    # -- public fetch ------------------------------------------------------- #
    def fetch(self, url: str, *, enforce_content_type: bool = True) -> FetchedPage:
        """GET a public URL, following a bounded number of validated redirects."""
        current = url
        for _ in range(self.config.max_redirects + 1):
            self._validate(current)
            status, headers, body, elapsed = self._attempt_with_retry(current)
            if status in _REDIRECT_CODES:
                location = headers.get("location")
                if not location:
                    raise CareerCollectorError(f"redirect {status} without Location header")
                current = urljoin(current, location)
                continue
            ctype = (headers.get("content-type", "") or "").split(";")[0].strip().lower()
            if enforce_content_type and ctype and ctype not in ALLOWED_CONTENT_TYPES:
                raise CareerCollectorError(f"unsupported content-type: {ctype}")
            return FetchedPage(url=current, status=status, content_type=ctype, text=body or "", elapsed_seconds=elapsed)
        raise CareerCollectorError(f"too many redirects (> {self.config.max_redirects})")

    def _attempt_with_retry(self, url: str):
        client = self._client()
        host = urlsplit(url).hostname
        started = time.monotonic()
        try:
            for attempt in range(1, self.retry.max_attempts + 1):
                if not self._limiter.allow():
                    logger.info("rate_limit_wait source=career host=%s", host)
                    self._sleep(1.0)
                request = client.build_request("GET", url, headers=self._headers())
                response = client.send(request, stream=True)
                try:
                    status = response.status_code
                    logger.info("request source=career host=%s status=%s attempt=%s", host, status, attempt)
                    if status in _REDIRECT_CODES:
                        return status, response.headers, None, round(time.monotonic() - started, 3)
                    if status == 200:
                        body = self._read_capped(response)
                        return status, response.headers, body, round(time.monotonic() - started, 3)
                    if attempt < self.retry.max_attempts and self.retry.is_retryable(status):
                        wait = self._retry_after(response) if status == 429 else self.retry.backoff_for(attempt)
                        logger.warning("retry source=career host=%s status=%s wait=%s", host, status, wait)
                        self._sleep(wait)
                        continue
                    if status == 403:
                        raise RestrictedError(f"access restricted (HTTP 403) for host {host}")
                    raise CareerCollectorError(f"request failed with HTTP {status} for host {host}")
                finally:
                    response.close()
            raise CareerCollectorError("request exhausted retries")
        finally:
            if self._http is None:
                client.close()

    def _retry_after(self, response: httpx.Response) -> float:
        header = response.headers.get("Retry-After", "")
        if header.isdigit():
            return min(float(header), self.retry.backoff_max_seconds)
        return self.retry.backoff_for(1)

    def try_fetch_text(self, url: str) -> Optional[str]:
        """Best-effort GET returning text, or None on any safety/HTTP failure.

        Used for robots.txt, where absence/failure means 'unknown', not an error.
        Content-type is not enforced here since robots.txt is served as text/plain.
        """
        try:
            return self.fetch(url, enforce_content_type=False).text
        except (SafetyError, CareerCollectorError, httpx.HTTPError):
            return None
