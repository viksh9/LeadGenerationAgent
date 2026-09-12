"""Low-level ContactOut HTTP client (network logic only; no business logic).

Centralizes authentication (the documented `token` header — never a query param),
client-side rate limiting (People Search 60/min, other APIs 1000/min — configurable),
timeouts, and a safe retry policy (transient 429/5xx only, honouring Retry-After
with capped exponential backoff — no retry storms). The API token is NEVER logged,
returned, or included in any exception message.

Endpoints (per the documented ContactOut API contract):
    GET  /v1/people/decision-makers
    POST /v1/people/search
    POST /v1/people/enrich

NOTE: exact response field names vary by ContactOut plan/version; the mapper
(`mapper.py`) parses defensively and never fabricates missing values.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Any, Callable, Optional

import httpx

from collectors.base import HealthStatus, RateLimiter, RetryConfig, TimeoutConfig
from config import get_settings
from integrations.contactout.exceptions import (
    ContactOutAuthError,
    ContactOutBadResponse,
    ContactOutNotConfigured,
    ContactOutRateLimitError,
    ContactOutUnavailableError,
)

logger = logging.getLogger("integrations.contactout")

# httpx/httpcore echo full URLs (and could echo headers at DEBUG) — keep them quiet.
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)

_PEOPLE_SEARCH_PATH = "/v1/people/search"
_DECISION_MAKERS_PATH = "/v1/people/decision-makers"
_ENRICH_PATH = "/v1/people/enrich"
# Lightweight authenticated endpoint used only for connectivity checks so a test
# never spends enrichment credits. Confirm against live ContactOut docs (REQUIRES
# REVIEW) — configurable via CONTACTOUT_HEALTH_PATH if it differs.
_DEFAULT_HEALTH_PATH = "/v1/stats"


@dataclass
class ContactOutConfig:
    """Client configuration — sourced from Settings, never hard-coded."""

    api_token: Optional[str]
    base_url: str = "https://api.contactout.com"
    timeout_seconds: float = 20.0
    people_search_rpm: int = 60
    other_rpm: int = 1000
    max_retries: int = 3
    backoff_cap_seconds: float = 30.0
    health_path: str = _DEFAULT_HEALTH_PATH

    @property
    def is_configured(self) -> bool:
        return bool(self.api_token)


def load_contactout_config() -> ContactOutConfig:
    """Build client config from application settings (environment-driven)."""
    s = get_settings()
    return ContactOutConfig(
        api_token=s.contactout_api_token,
        base_url=(s.contactout_base_url or "https://api.contactout.com").rstrip("/"),
        timeout_seconds=s.contactout_timeout_seconds,
        people_search_rpm=s.contactout_people_search_rate_per_minute,
        other_rpm=s.contactout_other_rate_per_minute,
        max_retries=s.contactout_max_retries,
        backoff_cap_seconds=s.contactout_backoff_cap_seconds,
    )


class ContactOutClient:
    """Typed ContactOut API client. All auth is centralized here."""

    def __init__(
        self,
        config: Optional[ContactOutConfig] = None,
        *,
        timeout: TimeoutConfig | None = None,
        http: httpx.Client | None = None,
        sleep: Callable[[float], None] = time.sleep,
        search_limiter: RateLimiter | None = None,
        other_limiter: RateLimiter | None = None,
    ) -> None:
        self.config = config or load_contactout_config()
        self.retry = RetryConfig(max_attempts=max(1, self.config.max_retries),
                                 backoff_max_seconds=self.config.backoff_cap_seconds)
        self.timeout = timeout or TimeoutConfig(read_timeout=self.config.timeout_seconds)
        self._http = http
        self._sleep = sleep
        # People Search has a stricter documented limit than the other APIs.
        self._search_limiter = search_limiter or RateLimiter(self.config.people_search_rpm)
        self._other_limiter = other_limiter or RateLimiter(self.config.other_rpm)

    # --- public typed methods ------------------------------------------------ #
    def get_decision_makers(self, *, linkedin_url: Optional[str] = None,
                            domain: Optional[str] = None, name: Optional[str] = None,
                            page: int = 1, page_size: int = 25) -> dict[str, Any]:
        """GET /v1/people/decision-makers. At least one company identifier required."""
        if not (linkedin_url or domain or name):
            raise ContactOutBadResponse("Decision Makers requires a company identifier.")
        params: dict[str, Any] = {"page": page, "page_size": page_size}
        if linkedin_url:
            params["linkedin_url"] = linkedin_url
        if domain:
            params["domain"] = domain
        if name:
            params["name"] = name
        return self._request("GET", _DECISION_MAKERS_PATH, params=params,
                             limiter=self._other_limiter, endpoint="decision-makers")

    def search_people(self, *, job_title: Optional[list[str] | str] = None,
                      job_function: Optional[str] = None, seniority: Optional[list[str] | str] = None,
                      company: Optional[str] = None, location: Optional[str] = None,
                      skills: Optional[list[str]] = None, current_titles_only: bool = True,
                      page: int = 1, page_size: int = 25) -> dict[str, Any]:
        """POST /v1/people/search — scoped to a company wherever possible."""
        body: dict[str, Any] = {"current_titles_only": current_titles_only,
                                "page": page, "page_size": page_size}
        if job_title:
            body["job_title"] = job_title
        if job_function:
            body["job_function"] = job_function
        if seniority:
            body["seniority"] = seniority
        if company:
            body["company"] = company
        if location:
            body["location"] = location
        if skills:
            body["skills"] = skills
        return self._request("POST", _PEOPLE_SEARCH_PATH, json=body,
                             limiter=self._search_limiter, endpoint="people-search")

    def enrich_person(self, *, linkedin_url: Optional[str] = None, email: Optional[str] = None,
                     phone: Optional[str] = None, full_name: Optional[str] = None,
                     first_name: Optional[str] = None, last_name: Optional[str] = None,
                     company: Optional[str] = None, company_domain: Optional[str] = None,
                     job_title: Optional[str] = None, location: Optional[str] = None) -> dict[str, Any]:
        """POST /v1/people/enrich — only ever with real identifiers (never fabricated)."""
        body = {k: v for k, v in {
            "linkedin_url": linkedin_url, "email": email, "phone": phone,
            "full_name": full_name, "first_name": first_name, "last_name": last_name,
            "company": company, "company_domain": company_domain,
            "job_title": job_title, "location": location,
        }.items() if v}
        if not body:
            raise ContactOutBadResponse("Enrich requires at least one real identifier.")
        return self._request("POST", _ENRICH_PATH, json=body,
                             limiter=self._other_limiter, endpoint="enrich")

    def check_connection(self) -> tuple[HealthStatus, str]:
        """Cheap authenticated connectivity check (no enrichment credits). Returns a
        (HealthStatus, message) pair; never raises. Reports NOT_CONFIGURED without a
        token and only CONNECTED after a real authenticated 2xx."""
        if not self.config.is_configured:
            return HealthStatus.NOT_CONFIGURED, "No ContactOut API token configured."
        url = f"{self.config.base_url}{self.config.health_path}"
        client = self._client()
        try:
            resp = client.get(url, headers=self._headers())
            status = resp.status_code
            logger.info("contactout.request endpoint=health status_code=%s", status)
            if 200 <= status < 300:
                return HealthStatus.HEALTHY, "ContactOut reachable and authenticated."
            if status in (401, 403):
                return HealthStatus.AUTHENTICATION_FAILED, "ContactOut rejected the API token."
            if status == 429:
                return HealthStatus.RATE_LIMITED, "ContactOut rate limit reached."
            return HealthStatus.UNAVAILABLE, f"ContactOut returned HTTP {status}."
        except (httpx.TimeoutException, httpx.HTTPError) as exc:
            logger.warning("contactout.error endpoint=health reason=%s", type(exc).__name__)
            return HealthStatus.UNAVAILABLE, "ContactOut request failed (network/timeout)."
        finally:
            if self._http is None:
                client.close()

    # --- internals ----------------------------------------------------------- #
    def _headers(self) -> dict[str, str]:
        # Documented ContactOut auth header. NEVER a query param; NEVER logged.
        return {"token": self.config.api_token or "", "Content-Type": "application/json",
                "Accept": "application/json"}

    def _client(self) -> httpx.Client:
        if self._http is not None:
            return self._http
        return httpx.Client(
            timeout=httpx.Timeout(self.timeout.read_timeout, connect=self.timeout.connect_timeout)
        )

    def _request(self, method: str, path: str, *, endpoint: str, limiter: RateLimiter,
                 params: Optional[dict] = None, json: Optional[dict] = None) -> dict[str, Any]:
        if not self.config.is_configured:
            raise ContactOutNotConfigured("CONTACTOUT_API_TOKEN is not configured.")
        url = f"{self.config.base_url}{path}"
        client = self._client()
        try:
            for attempt in range(1, self.retry.max_attempts + 1):
                if not limiter.allow():
                    logger.info("contactout.rate_limit_wait endpoint=%s", endpoint)
                    self._sleep(1.0)
                logger.info("contactout.request endpoint=%s attempt=%s", endpoint, attempt)
                response = client.request(method, url, headers=self._headers(),
                                          params=params, json=json)
                status = response.status_code
                if 200 <= status < 300:
                    logger.info("contactout.success endpoint=%s status_code=%s", endpoint, status)
                    try:
                        return response.json()
                    except ValueError as exc:  # noqa: BLE001 - invalid JSON body
                        raise ContactOutBadResponse(
                            f"ContactOut {endpoint} returned an unparseable response.") from exc
                if status in (401, 403):
                    logger.warning("contactout.error endpoint=%s status_code=%s reason=auth", endpoint, status)
                    raise ContactOutAuthError(f"ContactOut authentication failed (HTTP {status}).")
                if attempt < self.retry.max_attempts and (status == 429 or self.retry.is_retryable(status)):
                    wait = self._retry_after(response) if status == 429 else self.retry.backoff_for(attempt)
                    logger.warning("contactout.rate_limited endpoint=%s status_code=%s attempt=%s retry_after=%s",
                                   endpoint, status, attempt, wait)
                    self._sleep(wait)
                    continue
                if status == 429:
                    raise ContactOutRateLimitError("ContactOut rate limit exceeded (HTTP 429).",
                                                   retry_after=self._retry_after(response))
                if self.retry.is_retryable(status):
                    raise ContactOutUnavailableError(f"ContactOut temporarily unavailable (HTTP {status}).")
                logger.warning("contactout.error endpoint=%s status_code=%s", endpoint, status)
                raise ContactOutUnavailableError(f"ContactOut {endpoint} failed with HTTP {status}.")
            raise ContactOutUnavailableError(f"ContactOut {endpoint} exhausted retries.")
        except (httpx.TimeoutException, httpx.HTTPError) as exc:
            logger.warning("contactout.error endpoint=%s reason=%s", endpoint, type(exc).__name__)
            raise ContactOutUnavailableError("ContactOut request failed (network/timeout).") from exc
        finally:
            if self._http is None:
                client.close()

    def _retry_after(self, response: httpx.Response) -> float:
        header = response.headers.get("Retry-After", "")
        if header.isdigit():
            return min(float(header), self.retry.backoff_max_seconds)
        return self.retry.backoff_for(1)
