"""Adzuna jobs collector — the first real IT job-data collector.

Collects raw job postings from the Adzuna public jobs API and returns them as
`RawRecordDraft`s. It ONLY collects — no scoring/signal logic (technology/role
extraction is left to the downstream normalization step). Credentials come from
the environment and are never logged or serialized:

    SOURCE_ADZUNA_APP_ID     Adzuna application id
    SOURCE_ADZUNA_API_KEY    Adzuna application key
    SOURCE_ADZUNA_COUNTRY    optional country code (default: gb)

Network calls respect the source's rate limit, timeouts, and a safe retry policy
(transient 429/5xx only — never auth or other 4xx).
"""

from __future__ import annotations

import logging
import os
import time
from datetime import datetime, timezone
from typing import Any, Callable, Optional

import httpx

from collectors.base import BaseCollector, CollectorResult, FetchRequest, HealthCheckResult, HealthStatus, RateLimiter
from collectors.raw_record import RawRecordDraft
from collectors.source_registry import SourceDefinition

logger = logging.getLogger("collectors")

# Adzuna requires credentials as query params; httpx/httpcore echo the full URL
# in their INFO/DEBUG logs, which would leak the key. Quiet them (see §20).
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)

DEFAULT_WHAT = "software engineer"
DEFAULT_COUNTRY = "gb"
MAX_RESULTS_PER_PAGE = 50


class CollectorError(RuntimeError):
    """Raised for unrecoverable collector failures (config or non-retryable HTTP)."""


class AdzunaCollector(BaseCollector):
    def __init__(
        self,
        source: SourceDefinition,
        *,
        client: httpx.Client | None = None,
        sleep: Callable[[float], None] = time.sleep,
        **kwargs: Any,
    ) -> None:
        super().__init__(source, **kwargs)
        self._client = client
        self._sleep = sleep
        self._limiter = RateLimiter(self.rate_limit.requests_per_minute)

    # -- credentials (never logged) ----------------------------------------- #
    def _credentials(self) -> Optional[tuple[str, str]]:
        app_id = os.environ.get("SOURCE_ADZUNA_APP_ID")
        app_key = os.environ.get("SOURCE_ADZUNA_API_KEY")
        return (app_id, app_key) if app_id and app_key else None

    def _country(self) -> str:
        return os.environ.get("SOURCE_ADZUNA_COUNTRY", DEFAULT_COUNTRY)

    def _http(self) -> httpx.Client:
        if self._client is not None:
            return self._client
        return httpx.Client(
            timeout=httpx.Timeout(self.timeout.read_timeout, connect=self.timeout.connect_timeout)
        )

    # -- request with safe retry -------------------------------------------- #
    def _get_json(self, url: str, params: dict[str, Any]) -> dict[str, Any]:
        safe_params = {k: v for k, v in params.items() if k not in {"app_id", "app_key"}}
        client = self._http()
        try:
            for attempt in range(1, self.retry.max_attempts + 1):
                if not self._limiter.allow():
                    self._sleep(1.0)
                logger.info("collector_request source_id=%s params=%s attempt=%s", self.source_id, safe_params, attempt)
                response = client.get(url, params=params)
                status = response.status_code
                if status == 200:
                    return response.json()
                if self.retry.is_retryable(status) and attempt < self.retry.max_attempts:
                    logger.warning("collector_retry source_id=%s status=%s attempt=%s", self.source_id, status, attempt)
                    self._sleep(self.retry.backoff_for(attempt))
                    continue
                logger.error("collector_error source_id=%s status=%s", self.source_id, status)
                raise CollectorError(f"Adzuna request failed with HTTP {status}")
            raise CollectorError("Adzuna request exhausted retries")
        finally:
            if self._client is None:
                client.close()

    # -- mapping ------------------------------------------------------------ #
    @staticmethod
    def _parse_dt(value: Any) -> Optional[datetime]:
        if not value or not isinstance(value, str):
            return None
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None

    def _to_draft(self, item: dict[str, Any]) -> RawRecordDraft:
        company = (item.get("company") or {}).get("display_name")
        location = (item.get("location") or {}).get("display_name")
        salary_min, salary_max = item.get("salary_min"), item.get("salary_max")
        salary = None
        if salary_min or salary_max:
            salary = f"{int(salary_min) if salary_min else '?'}-{int(salary_max) if salary_max else '?'}"
        return RawRecordDraft(
            source_id=self.source_id,
            external_id=str(item["id"]) if item.get("id") is not None else None,
            source_url=item.get("redirect_url"),
            published_at=self._parse_dt(item.get("created")),
            record_type="JOB_POSTING",
            title=item.get("title"),
            description=item.get("description"),
            company_name=company,
            location=location,
            industry=(item.get("category") or {}).get("label"),
            salary=salary,
            raw_payload=item,
            is_synthetic=False,  # real production record
        )

    # -- public API --------------------------------------------------------- #
    def fetch(self, request: FetchRequest | None = None) -> CollectorResult:
        creds = self._credentials()
        if creds is None:
            raise CollectorError("Adzuna is not configured (missing SOURCE_ADZUNA_APP_ID / SOURCE_ADZUNA_API_KEY).")
        app_id, app_key = creds
        req = request or FetchRequest()
        page = req.page or 1
        per_page = min(req.limit or 20, MAX_RESULTS_PER_PAGE)
        params: dict[str, Any] = {
            "app_id": app_id,
            "app_key": app_key,
            "results_per_page": per_page,
            "what": req.query or DEFAULT_WHAT,
            "content-type": "application/json",
            "sort_by": "date",
        }
        if req.since is not None:
            days = max(0, (datetime.now(timezone.utc) - req.since).days)
            params["max_days_old"] = days

        url = f"{self.source.base_url}/jobs/{self._country()}/search/{page}"
        started = time.monotonic()
        logger.info("collector_started source_id=%s page=%s", self.source_id, page)
        payload = self._get_json(url, params)

        items = payload.get("results", []) or []
        drafts: list[RawRecordDraft] = []
        warnings: list[str] = []
        for item in items:
            try:
                drafts.append(self._to_draft(item))
            except Exception as exc:  # noqa: BLE001 - skip a bad record, keep the batch
                warnings.append(f"skipped a record: {exc}")

        total = payload.get("count")
        has_more = bool(total is not None and page * per_page < total)
        duration = round(time.monotonic() - started, 3)
        logger.info(
            "collector_completed source_id=%s page=%s records_count=%s duration=%s",
            self.source_id, page, len(drafts), duration,
        )
        return CollectorResult(
            source_id=self.source_id,
            records=drafts,
            page=page,
            next_cursor=str(page + 1) if has_more else None,
            has_more=has_more,
            total_records=total,
            warnings=warnings,
        )

    def fetch_incremental(self, request: FetchRequest | None = None) -> CollectorResult:
        """Adzuna supports a date filter — pass `since` to limit to recent postings."""
        return self.fetch(request)

    def health_check(self) -> HealthCheckResult:
        if self._credentials() is None:
            return HealthCheckResult(
                source_id=self.source_id,
                status=HealthStatus.NOT_CONFIGURED,
                message="API credentials not configured.",
            )
        try:
            self.fetch(FetchRequest(limit=1))
        except CollectorError as exc:
            return HealthCheckResult(
                source_id=self.source_id, status=HealthStatus.UNAVAILABLE, message=str(exc)
            )
        return HealthCheckResult(source_id=self.source_id, status=HealthStatus.HEALTHY, message="OK")
