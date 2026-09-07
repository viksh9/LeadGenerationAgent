"""Jooble Jobs API collector (real source; India-first, IT-focused).

Implements the Jooble REST contract verified from the official docs:
  POST https://{host}/api/{api_key}
  body: {"keywords": <str>, "location": <str>, "page": <int>, "radius": <str>,
         "salary": <int>, "SearchMode": <int>, "companysearch": <bool>}
  resp: {"totalCount": <int>,
         "jobs": [{id,title,location,snippet,salary,source,type,link,company,updated}]}

Notes / honesty:
  * Credentials come from JOOBLE_API_KEY (never hard-coded/logged — the key sits in
    the URL path, which is redacted in logs).
  * Keys are per-country domain: an India key from in.jooble.org is required for
    Indian listings (JOOBLE_API_HOST). The FREE plan is a hard 500-request lifetime
    cap per key — defaults here are deliberately conservative.
  * The collector returns raw records only; no scoring/business logic. Failures
    surface as typed errors (auth/rate-limit/unavailable), never as fake data.
"""

from __future__ import annotations

import html
import logging
import re
import time
from datetime import datetime, timezone
from typing import Any, Callable, Optional

import httpx
from pydantic import BaseModel

from collectors.base import (
    BaseCollector,
    CollectorResult,
    FetchRequest,
    HealthCheckResult,
    HealthStatus,
    RateLimiter,
    RetryConfig,
    TimeoutConfig,
)
from collectors.errors import (
    CollectorError,
    SourceAuthError,
    SourceRateLimitError,
    SourceUnavailableError,
)
from collectors.it_taxonomy import NOT_RELEVANT, classify_it_relevance
from collectors.jobs.config import DEFAULT_LOCATIONS, DEFAULT_SEARCH_TERMS
from collectors.raw_record import RawRecordDraft
from collectors.source_registry import SourceDefinition

logger = logging.getLogger("collectors")
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)

SOURCE_ID = "jooble"
COLLECTOR_VERSION = "1.0.0"
MAX_RESULTS_PER_PAGE = 50
_ALLOWED_RADIUS = {0, 4, 8, 16, 26, 40, 80}


# --------------------------------------------------------------------------- #
# Configuration (environment-based; no secrets in code)
# --------------------------------------------------------------------------- #
class JoobleConfig(BaseModel):
    api_key: Optional[str] = None
    # Per-country domain host. Indian listings require an India-domain key + host.
    host: str = "jooble.org"
    location: str = "India"          # India-wide default; per-city via FetchRequest
    search_terms: list[str] = list(DEFAULT_SEARCH_TERMS)
    locations: list[str] = list(DEFAULT_LOCATIONS)
    results_per_page: int = 20
    max_pages: int = 3               # conservative: free plan is 500 lifetime calls
    radius: Optional[int] = None
    requests_per_minute: int = 10
    daily_request_limit: int = 100
    # Hard LIFETIME request budget per key (free plan = 500, absolute). Enforced
    # persistently via collectors.source_budget so the quota can't be burned.
    lifetime_request_budget: int = 500
    timeout_seconds: float = 15.0

    @property
    def is_configured(self) -> bool:
        return bool(self.api_key)

    @property
    def base_url(self) -> str:
        return f"https://{self.host}/api"


def _env_list(key: str, default: tuple[str, ...]) -> list[str]:
    value = __import__("os").environ.get(key)
    if not value:
        return list(default)
    return [item.strip() for item in value.split(",") if item.strip()]


def _env_int(key: str, default: int) -> int:
    import os

    try:
        return int(os.environ.get(key, default))
    except (TypeError, ValueError):
        return default


def load_jooble_config() -> JoobleConfig:
    import os

    radius = os.environ.get("JOOBLE_RADIUS")
    return JoobleConfig(
        api_key=os.environ.get("JOOBLE_API_KEY") or None,
        host=os.environ.get("JOOBLE_API_HOST", "jooble.org").strip() or "jooble.org",
        location=os.environ.get("JOOBLE_LOCATION", "India").strip() or "India",
        search_terms=_env_list("JOOBLE_SEARCH_TERMS", DEFAULT_SEARCH_TERMS),
        locations=_env_list("JOOBLE_LOCATIONS", DEFAULT_LOCATIONS),
        results_per_page=_env_int("JOOBLE_RESULTS_PER_PAGE", 20),
        max_pages=_env_int("JOOBLE_MAX_PAGES", 3),
        radius=int(radius) if radius and radius.isdigit() else None,
        requests_per_minute=_env_int("JOOBLE_REQUESTS_PER_MINUTE", 10),
        daily_request_limit=_env_int("JOOBLE_DAILY_REQUEST_LIMIT", 100),
        lifetime_request_budget=_env_int("JOOBLE_LIFETIME_REQUEST_BUDGET", 500),
        timeout_seconds=float(os.environ.get("JOOBLE_TIMEOUT_SECONDS", 15)),
    )


# --------------------------------------------------------------------------- #
# HTTP client (network only; credentials never logged)
# --------------------------------------------------------------------------- #
class JoobleClient:
    def __init__(
        self,
        config: JoobleConfig,
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

    def search(self, body: dict[str, Any]) -> dict[str, Any]:
        """POST /api/{key} with a JSON body. The key (in the URL) is never logged."""
        if not self.config.api_key:
            raise CollectorError("Jooble is not configured (missing JOOBLE_API_KEY).")
        url = f"{self.config.base_url}/{self.config.api_key}"
        redacted = f"{self.config.base_url}/***"
        client = self._client()
        try:
            for attempt in range(1, self.retry.max_attempts + 1):
                if not self._limiter.allow():
                    logger.info("rate_limit_wait source_id=jooble")
                    self._sleep(1.0)
                logger.info("request_started source_id=jooble url=%s page=%s attempt=%s",
                            redacted, body.get("page"), attempt)
                response = client.post(url, json=body)
                status = response.status_code
                if status == 200:
                    logger.info("request_completed source_id=jooble status=200")
                    try:
                        return response.json()
                    except ValueError as exc:
                        raise CollectorError(f"Jooble returned malformed JSON: {exc}") from exc
                if status in (401, 403):
                    logger.error("collector_auth_failed source_id=jooble status=%s", status)
                    raise SourceAuthError(f"Jooble authentication failed (HTTP {status}).")
                if attempt < self.retry.max_attempts and (status == 429 or self.retry.is_retryable(status)):
                    wait = self._retry_after(response) if status == 429 else self.retry.backoff_for(attempt)
                    logger.warning("retry source_id=jooble status=%s attempt=%s wait=%s", status, attempt, wait)
                    self._sleep(wait)
                    continue
                logger.error("collector_failed source_id=jooble status=%s", status)
                if status == 429:
                    raise SourceRateLimitError("Jooble rate limit exceeded (HTTP 429).")
                if self.retry.is_retryable(status):
                    raise SourceUnavailableError(f"Jooble temporarily unavailable (HTTP {status}).")
                raise CollectorError(f"Jooble request failed with HTTP {status}")
            raise SourceUnavailableError("Jooble request exhausted retries.")
        except httpx.HTTPError as exc:
            raise SourceUnavailableError(f"Jooble network error: {exc}") from exc
        finally:
            if self._http is None:
                client.close()

    def _retry_after(self, response: httpx.Response) -> float:
        header = response.headers.get("Retry-After", "")
        if header.isdigit():
            return min(float(header), self.retry.backoff_max_seconds)
        return self.retry.backoff_for(1)


# --------------------------------------------------------------------------- #
# Mapping (Jooble job → RawRecordDraft). Missing fields stay NULL — never faked.
# --------------------------------------------------------------------------- #
_TAG_RE = re.compile(r"<[^>]+>")


def _clean(text: Optional[str]) -> Optional[str]:
    if not text:
        return None
    # Unescape entities first, then strip tags (handles escaped or raw HTML).
    stripped = _TAG_RE.sub(" ", html.unescape(text))
    stripped = re.sub(r"\s+", " ", stripped).strip()
    return stripped or None


def _parse_dt(value: Any) -> Optional[datetime]:
    if not value or not isinstance(value, str):
        return None
    text = value.strip().replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(text)
    except ValueError:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def map_job(item: dict[str, Any], *, host: str, query: str, location: Optional[str]) -> RawRecordDraft:
    external_id = str(item["id"]) if item.get("id") is not None else None
    payload = dict(item)
    payload["_collection"] = {
        "collector": SOURCE_ID, "collector_version": COLLECTOR_VERSION,
        "host": host, "query": query, "searched_location": location,
    }
    return RawRecordDraft(
        source_id=SOURCE_ID,
        external_id=external_id,
        source_url=item.get("link"),
        published_at=_parse_dt(item.get("updated")),
        record_type="JOB_POSTING",
        title=_clean(item.get("title")),
        description=_clean(item.get("snippet")),
        company_name=(item.get("company") or None) or None,
        location=item.get("location") or None,
        salary=(item.get("salary") or None) or None,
        contract_type=item.get("type") or None,
        raw_payload=payload,
        is_synthetic=False,
    )


def is_it_relevant(item: dict[str, Any]) -> bool:
    """Keep RELEVANT/UNKNOWN, drop clearly NOT_RELEVANT (collection optimization only)."""
    return classify_it_relevance(item.get("title"), item.get("snippet")) != NOT_RELEVANT


# --------------------------------------------------------------------------- #
# Collector
# --------------------------------------------------------------------------- #
class JoobleJobCollector(BaseCollector):
    def __init__(
        self,
        source: SourceDefinition,
        *,
        config: JoobleConfig | None = None,
        client: JoobleClient | None = None,
        http: httpx.Client | None = None,
        sleep=time.sleep,
        **kwargs,
    ) -> None:
        super().__init__(source, **kwargs)
        self.config = config or load_jooble_config()
        self._client = client or JoobleClient(
            self.config, retry=self.retry, timeout=self.timeout, http=http, sleep=sleep
        )

    def _build_body(self, request: FetchRequest) -> dict[str, Any]:
        keywords = request.query or (self.config.search_terms[0] if self.config.search_terms
                                     else "software engineer")
        location = request.location or self.config.location
        per_page = min(request.limit or self.config.results_per_page, MAX_RESULTS_PER_PAGE)
        body: dict[str, Any] = {
            "keywords": keywords,
            "location": location,
            "page": request.page or 1,
            "ResultOnPage": per_page,
        }
        if self.config.radius in _ALLOWED_RADIUS and self.config.radius is not None:
            body["radius"] = str(self.config.radius)
        return body

    def fetch(self, request: FetchRequest | None = None) -> CollectorResult:
        if not self.config.is_configured:
            raise CollectorError("Jooble is not configured (missing JOOBLE_API_KEY).")
        req = request or FetchRequest()
        body = self._build_body(req)
        started = time.monotonic()
        logger.info("collector_started source_id=jooble query=%r location=%r page=%s",
                    body["keywords"], body["location"], body["page"])
        payload = self._client.search(body)

        items = payload.get("jobs", []) or []
        records: list[RawRecordDraft] = []
        warnings: list[str] = []
        skipped_non_it = 0
        for item in items:
            if not isinstance(item, dict):
                continue
            if not is_it_relevant(item):
                skipped_non_it += 1
                continue
            try:
                records.append(map_job(item, host=self.config.host,
                                       query=body["keywords"], location=body["location"]))
            except Exception as exc:  # noqa: BLE001 - keep the batch going
                warnings.append(f"skipped a record: {exc}")
        if skipped_non_it:
            warnings.append(f"filtered {skipped_non_it} non-IT record(s)")

        total = payload.get("totalCount")
        page = body["page"]
        per_page = body["ResultOnPage"]
        has_more = bool(total is not None and page * per_page < total)
        duration = round(time.monotonic() - started, 3)
        logger.info("collector_completed source_id=jooble records_count=%s total=%s", len(records), total)
        return CollectorResult(
            source_id=SOURCE_ID,
            records=records,
            page=page,
            next_cursor=str(page + 1) if has_more else None,
            has_more=has_more,
            total_records=total,
            duration_seconds=duration,
            context={"query": body["keywords"], "location": body["location"], "host": self.config.host},
            warnings=warnings,
        )

    def plan_requests(self, *, max_pages: Optional[int] = None) -> list[FetchRequest]:
        """IT search plan (terms × pages) against the configured India location."""
        pages = max_pages or self.config.max_pages
        reqs: list[FetchRequest] = []
        for term in self.config.search_terms:
            for page in range(1, pages + 1):
                reqs.append(FetchRequest(query=term, location=self.config.location, page=page))
        return reqs

    def health_check(self) -> HealthCheckResult:
        if not self.config.is_configured:
            return HealthCheckResult(
                source_id=SOURCE_ID, status=HealthStatus.NOT_CONFIGURED,
                message="JOOBLE_API_KEY not configured.",
            )
        try:
            self._client.search({"keywords": "software engineer",
                                 "location": self.config.location, "page": 1, "ResultOnPage": 1})
        except SourceAuthError as exc:
            return HealthCheckResult(source_id=SOURCE_ID, status=HealthStatus.AUTHENTICATION_FAILED, message=str(exc))
        except SourceRateLimitError as exc:
            return HealthCheckResult(source_id=SOURCE_ID, status=HealthStatus.RATE_LIMITED, message=str(exc))
        except CollectorError as exc:
            return HealthCheckResult(source_id=SOURCE_ID, status=HealthStatus.UNAVAILABLE, message=str(exc))
        return HealthCheckResult(source_id=SOURCE_ID, status=HealthStatus.HEALTHY, message="OK")
