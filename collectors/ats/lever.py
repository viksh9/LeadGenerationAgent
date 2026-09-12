"""Lever public Postings API collector (official ATS source; no auth).

Verified contract (https://github.com/lever/postings-api):
  GET https://api.lever.co/v0/postings/{site}?mode=json[&limit=N&skip=M]
  -> [{id, text, categories:{location, team, commitment, department, allLocations},
       hostedUrl, applyUrl, createdAt(ms epoch), descriptionPlain, description,
       workplaceType, country, lists}]
  Public — only published postings are returned; no authentication required.

Official company career boards are higher-confidence DIRECT evidence (tier TIER_1).
The site handle identifies the company; we NEVER fabricate one — an unknown site is
DISCOVERY_REQUIRED. The host is fixed and the site handle is format-validated.
"""

from __future__ import annotations

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
from config.locations_in import is_india_location
from collectors.raw_record import RawRecordDraft
from collectors.source_registry import SourceDefinition

logger = logging.getLogger("collectors")
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)

SOURCE_ID = "lever"
COLLECTOR_VERSION = "1.0.0"
API_HOST = "https://api.lever.co/v0/postings"
_SITE_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{0,99}$")


def valid_site(site: Optional[str]) -> bool:
    return bool(site) and bool(_SITE_RE.match(site))


class LeverConfig(BaseModel):
    sites: list[str] = []                     # company site handles (env LEVER_SITES)
    results_per_site: int = 100
    requests_per_minute: int = 30
    timeout_seconds: float = 15.0
    india_only: bool = True   # India-first: keep only India-based roles (§15)
    it_only: bool = False     # ATS site = a known IT/tech company -> capture EVERY role.

    @property
    def is_configured(self) -> bool:
        return any(valid_site(s) for s in self.sites)


def load_lever_config() -> LeverConfig:
    import os

    raw = os.environ.get("LEVER_SITES", "")
    sites = [s.strip() for s in raw.split(",") if s.strip()]
    return LeverConfig(
        sites=sites,
        results_per_site=int(os.environ.get("LEVER_RESULTS_PER_SITE", 100) or 100),
        requests_per_minute=int(os.environ.get("LEVER_REQUESTS_PER_MINUTE", 30) or 30),
        timeout_seconds=float(os.environ.get("LEVER_TIMEOUT_SECONDS", 15) or 15),
        india_only=(os.environ.get("ATS_INDIA_ONLY", "true").strip().lower() not in ("false", "0", "no")),
        it_only=(os.environ.get("ATS_IT_ONLY", "false").strip().lower() in ("true", "1", "yes")),
    )


def _parse_created(value: Any) -> Optional[datetime]:
    """Lever createdAt is epoch milliseconds."""
    if not isinstance(value, (int, float)):
        return None
    try:
        return datetime.fromtimestamp(value / 1000.0, tz=timezone.utc)
    except (ValueError, OverflowError, OSError):
        return None


class LeverClient:
    def __init__(
        self, config: LeverConfig, *, retry: RetryConfig | None = None,
        timeout: TimeoutConfig | None = None, http: httpx.Client | None = None,
        sleep: Callable[[float], None] = time.sleep, limiter: RateLimiter | None = None,
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

    def list_postings(self, site: str, *, limit: int, skip: int = 0) -> list[dict[str, Any]]:
        if not valid_site(site):
            raise CollectorError(f"Invalid Lever site handle: {site!r}")
        url = f"{API_HOST}/{site}"
        params = {"mode": "json", "limit": limit, "skip": skip}
        client = self._client()
        try:
            for attempt in range(1, self.retry.max_attempts + 1):
                if not self._limiter.allow():
                    self._sleep(1.0)
                logger.info("request_started source_id=lever site=%s attempt=%s", site, attempt)
                resp = client.get(url, params=params)
                status = resp.status_code
                if status == 200:
                    try:
                        data = resp.json()
                    except ValueError as exc:
                        raise CollectorError(f"Lever returned malformed JSON: {exc}") from exc
                    return data if isinstance(data, list) else []
                if status in (401, 403):
                    raise SourceAuthError(f"Lever access denied (HTTP {status}).")
                if status == 404:
                    raise CollectorError(f"Lever site not found: {site!r} (HTTP 404).")
                if attempt < self.retry.max_attempts and self.retry.is_retryable(status):
                    self._sleep(self.retry.backoff_for(attempt))
                    continue
                if status == 429:
                    raise SourceRateLimitError("Lever rate limit exceeded (HTTP 429).")
                if self.retry.is_retryable(status):
                    raise SourceUnavailableError(f"Lever unavailable (HTTP {status}).")
                raise CollectorError(f"Lever request failed with HTTP {status}")
            raise SourceUnavailableError("Lever request exhausted retries.")
        except httpx.HTTPError as exc:
            raise SourceUnavailableError(f"Lever network error: {exc}") from exc
        finally:
            if self._http is None:
                client.close()


def map_job(item: dict[str, Any], site: str) -> RawRecordDraft:
    cats = item.get("categories") or {}
    payload = dict(item)
    payload["_collection"] = {"collector": SOURCE_ID, "collector_version": COLLECTOR_VERSION, "site": site}
    return RawRecordDraft(
        source_id=SOURCE_ID,
        external_id=str(item["id"]) if item.get("id") is not None else None,
        source_url=item.get("hostedUrl"),
        published_at=_parse_created(item.get("createdAt")),
        record_type="JOB_POSTING",
        title=(item.get("text") or None),
        description=(item.get("descriptionPlain") or None),
        # Lever postings carry no company display name; the site handle is the
        # company's own board identifier — resolution normalizes it.
        company_name=site,
        location=(cats.get("location") or None),
        contract_type=(cats.get("commitment") or None),
        raw_payload=payload,
        is_synthetic=False,
    )


def _is_india_job(item: dict[str, Any]) -> bool:
    """True when a Lever posting is in India — checks categories.location plus
    categories.allLocations (multi-location roles count if any is in India)."""
    cats = item.get("categories") or {}
    loc = cats.get("location") or ""
    all_locs = cats.get("allLocations") or []
    extra = " ".join(str(x) for x in all_locs) if isinstance(all_locs, list) else str(all_locs)
    return is_india_location(f"{loc} {extra}")


def is_it_relevant(item: dict[str, Any]) -> bool:
    return classify_it_relevance(item.get("text"), item.get("descriptionPlain")) != NOT_RELEVANT


class LeverCollector(BaseCollector):
    def __init__(
        self, source: SourceDefinition, *, config: LeverConfig | None = None,
        client: LeverClient | None = None, http: httpx.Client | None = None,
        sleep=time.sleep, **kwargs,
    ) -> None:
        super().__init__(source, **kwargs)
        self.config = config or load_lever_config()
        self._client = client or LeverClient(
            self.config, retry=self.retry, timeout=self.timeout, http=http, sleep=sleep
        )

    def fetch(self, request: FetchRequest | None = None) -> CollectorResult:
        req = request or FetchRequest()
        site = req.board or (self.config.sites[0] if self.config.sites else None)
        if not site:
            raise CollectorError("Lever has no site configured (set LEVER_SITES).")
        started = time.monotonic()
        postings = self._client.list_postings(site, limit=req.limit or self.config.results_per_site)
        records: list[RawRecordDraft] = []
        warnings: list[str] = []
        skipped = 0
        skipped_non_india = 0
        for item in postings:
            if not isinstance(item, dict):
                continue
            if self.config.it_only and not is_it_relevant(item):
                skipped += 1
                continue
            if self.config.india_only and not _is_india_job(item):
                skipped_non_india += 1
                continue
            try:
                records.append(map_job(item, site))
            except Exception as exc:  # noqa: BLE001
                warnings.append(f"skipped a record: {exc}")
        if skipped:
            warnings.append(f"filtered {skipped} non-IT record(s)")
        if skipped_non_india:
            warnings.append(f"filtered {skipped_non_india} non-India record(s)")
        return CollectorResult(
            source_id=SOURCE_ID, records=records, page=1, has_more=False,
            total_records=len(postings), duration_seconds=round(time.monotonic() - started, 3),
            context={"site": site}, warnings=warnings,
        )

    def plan_requests(self, *, max_requests: Optional[int] = None, **_) -> list[FetchRequest]:
        sites = [s for s in self.config.sites if valid_site(s)]
        if max_requests:
            sites = sites[:max_requests]
        return [FetchRequest(board=s) for s in sites]

    def health_check(self) -> HealthCheckResult:
        sites = [s for s in self.config.sites if valid_site(s)]
        if not sites:
            return HealthCheckResult(source_id=SOURCE_ID, status=HealthStatus.NOT_CONFIGURED,
                                     message="No Lever site configured (DISCOVERY_REQUIRED).")
        try:
            self._client.list_postings(sites[0], limit=1)
        except SourceAuthError as exc:
            return HealthCheckResult(source_id=SOURCE_ID, status=HealthStatus.AUTHENTICATION_FAILED, message=str(exc))
        except SourceRateLimitError as exc:
            return HealthCheckResult(source_id=SOURCE_ID, status=HealthStatus.RATE_LIMITED, message=str(exc))
        except CollectorError as exc:
            return HealthCheckResult(source_id=SOURCE_ID, status=HealthStatus.UNAVAILABLE, message=str(exc))
        return HealthCheckResult(source_id=SOURCE_ID, status=HealthStatus.HEALTHY, message="OK")
