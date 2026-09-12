"""Greenhouse public Job Board API collector (official ATS source; no auth).

Verified contract (https://docs.greenhouse.io/job-board.html):
  GET https://boards-api.greenhouse.io/v1/boards/{board_token}/jobs?content=true
  -> {"jobs": [{id, title, updated_at, location:{name}, absolute_url, content,
                company_name, first_published, departments[], offices[], ...}],
      "meta": {"total": N}}
  Public — no authentication for GET job-board endpoints.

Official company career boards are higher-confidence DIRECT evidence than the
discovery aggregators (Adzuna/Jooble): evidence tier TIER_1. The board_token
identifies the company; we NEVER fabricate one — an unknown board is
DISCOVERY_REQUIRED. The API host is fixed, and board tokens are format-validated
to prevent path injection.
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
from config.locations_in import is_india_location
from collectors.raw_record import RawRecordDraft
from collectors.source_registry import SourceDefinition

logger = logging.getLogger("collectors")
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)

SOURCE_ID = "greenhouse"
COLLECTOR_VERSION = "1.0.0"
API_HOST = "https://boards-api.greenhouse.io/v1/boards"
# Greenhouse board tokens are lowercase alphanumeric with . _ - ; validate to
# keep the fixed host safe from path injection.
_BOARD_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{0,99}$")
_TAG_RE = re.compile(r"<[^>]+>")


def valid_board(token: Optional[str]) -> bool:
    return bool(token) and bool(_BOARD_RE.match(token))


class GreenhouseConfig(BaseModel):
    # Known company board tokens to collect (env GREENHOUSE_BOARDS, comma-sep).
    boards: list[str] = []
    requests_per_minute: int = 30
    timeout_seconds: float = 15.0
    max_records_per_board: int = 500
    india_only: bool = True   # India-first: keep only India-based roles (§15)

    @property
    def is_configured(self) -> bool:
        return any(valid_board(b) for b in self.boards)


def load_greenhouse_config() -> GreenhouseConfig:
    import os

    raw = os.environ.get("GREENHOUSE_BOARDS", "")
    boards = [b.strip() for b in raw.split(",") if b.strip()]
    return GreenhouseConfig(
        boards=boards,
        requests_per_minute=int(os.environ.get("GREENHOUSE_REQUESTS_PER_MINUTE", 30) or 30),
        timeout_seconds=float(os.environ.get("GREENHOUSE_TIMEOUT_SECONDS", 15) or 15),
        max_records_per_board=int(os.environ.get("GREENHOUSE_MAX_RECORDS", 500) or 500),
        india_only=(os.environ.get("ATS_INDIA_ONLY", "true").strip().lower() not in ("false", "0", "no")),
    )


def _clean(text: Optional[str]) -> Optional[str]:
    if not text:
        return None
    # Unescape first (Greenhouse returns HTML-escaped content), then strip tags.
    stripped = _TAG_RE.sub(" ", html.unescape(text))
    stripped = re.sub(r"\s+", " ", stripped).strip()
    return stripped or None


def _parse_dt(value: Any) -> Optional[datetime]:
    if not value or not isinstance(value, str):
        return None
    try:
        dt = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


class GreenhouseClient:
    def __init__(
        self, config: GreenhouseConfig, *, retry: RetryConfig | None = None,
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

    def list_jobs(self, board: str) -> dict[str, Any]:
        if not valid_board(board):
            raise CollectorError(f"Invalid Greenhouse board token: {board!r}")
        url = f"{API_HOST}/{board}/jobs"
        client = self._client()
        try:
            for attempt in range(1, self.retry.max_attempts + 1):
                if not self._limiter.allow():
                    self._sleep(1.0)
                logger.info("request_started source_id=greenhouse board=%s attempt=%s", board, attempt)
                resp = client.get(url, params={"content": "true"})
                status = resp.status_code
                if status == 200:
                    try:
                        return resp.json()
                    except ValueError as exc:
                        raise CollectorError(f"Greenhouse returned malformed JSON: {exc}") from exc
                if status in (401, 403):
                    raise SourceAuthError(f"Greenhouse access denied (HTTP {status}).")
                if status == 404:
                    raise CollectorError(f"Greenhouse board not found: {board!r} (HTTP 404).")
                if attempt < self.retry.max_attempts and self.retry.is_retryable(status):
                    self._sleep(self.retry.backoff_for(attempt))
                    continue
                if status == 429:
                    raise SourceRateLimitError("Greenhouse rate limit exceeded (HTTP 429).")
                if self.retry.is_retryable(status):
                    raise SourceUnavailableError(f"Greenhouse unavailable (HTTP {status}).")
                raise CollectorError(f"Greenhouse request failed with HTTP {status}")
            raise SourceUnavailableError("Greenhouse request exhausted retries.")
        except httpx.HTTPError as exc:
            raise SourceUnavailableError(f"Greenhouse network error: {exc}") from exc
        finally:
            if self._http is None:
                client.close()


def map_job(item: dict[str, Any], board: str) -> RawRecordDraft:
    payload = dict(item)
    payload["_collection"] = {"collector": SOURCE_ID, "collector_version": COLLECTOR_VERSION, "board": board}
    return RawRecordDraft(
        source_id=SOURCE_ID,
        external_id=str(item["id"]) if item.get("id") is not None else None,
        source_url=item.get("absolute_url"),
        published_at=_parse_dt(item.get("updated_at")) or _parse_dt(item.get("first_published")),
        record_type="JOB_POSTING",
        title=_clean(item.get("title")),
        description=_clean(item.get("content")),
        company_name=(item.get("company_name") or None),
        company_domain=None,
        location=(item.get("location") or {}).get("name") or None,
        raw_payload=payload,
        is_synthetic=False,
    )


def _is_india_job(item: dict[str, Any]) -> bool:
    """True when a Greenhouse job is in India — checks the primary location plus any
    listed offices (a multi-location role counts if any office is in India)."""
    loc = (item.get("location") or {}).get("name") or ""
    offices = " ".join(
        (o or {}).get("name") or "" for o in (item.get("offices") or []) if isinstance(o, dict))
    return is_india_location(f"{loc} {offices}")


def is_it_relevant(item: dict[str, Any]) -> bool:
    return classify_it_relevance(item.get("title"), _clean(item.get("content"))) != NOT_RELEVANT


class GreenhouseCollector(BaseCollector):
    def __init__(
        self, source: SourceDefinition, *, config: GreenhouseConfig | None = None,
        client: GreenhouseClient | None = None, http: httpx.Client | None = None,
        sleep=time.sleep, **kwargs,
    ) -> None:
        super().__init__(source, **kwargs)
        self.config = config or load_greenhouse_config()
        self._client = client or GreenhouseClient(
            self.config, retry=self.retry, timeout=self.timeout, http=http, sleep=sleep
        )

    def fetch(self, request: FetchRequest | None = None) -> CollectorResult:
        req = request or FetchRequest()
        board = req.board or (self.config.boards[0] if self.config.boards else None)
        if not board:
            raise CollectorError("Greenhouse has no board configured (set GREENHOUSE_BOARDS).")
        started = time.monotonic()
        payload = self._client.list_jobs(board)
        jobs = payload.get("jobs", []) or []
        records: list[RawRecordDraft] = []
        warnings: list[str] = []
        skipped = 0
        skipped_non_india = 0
        for item in jobs[: self.config.max_records_per_board]:
            if not isinstance(item, dict):
                continue
            if not is_it_relevant(item):
                skipped += 1
                continue
            if self.config.india_only and not _is_india_job(item):
                skipped_non_india += 1
                continue
            try:
                records.append(map_job(item, board))
            except Exception as exc:  # noqa: BLE001
                warnings.append(f"skipped a record: {exc}")
        if skipped:
            warnings.append(f"filtered {skipped} non-IT record(s)")
        if skipped_non_india:
            warnings.append(f"filtered {skipped_non_india} non-India record(s)")
        total = (payload.get("meta") or {}).get("total")
        return CollectorResult(
            source_id=SOURCE_ID, records=records, page=1, has_more=False,
            total_records=total, duration_seconds=round(time.monotonic() - started, 3),
            context={"board": board}, warnings=warnings,
        )

    def plan_requests(self, *, max_requests: Optional[int] = None, **_) -> list[FetchRequest]:
        """One request per configured board (Greenhouse returns all jobs at once)."""
        boards = [b for b in self.config.boards if valid_board(b)]
        if max_requests:
            boards = boards[:max_requests]
        return [FetchRequest(board=b) for b in boards]

    def health_check(self) -> HealthCheckResult:
        boards = [b for b in self.config.boards if valid_board(b)]
        if not boards:
            return HealthCheckResult(source_id=SOURCE_ID, status=HealthStatus.NOT_CONFIGURED,
                                     message="No Greenhouse board configured (DISCOVERY_REQUIRED).")
        try:
            self._client.list_jobs(boards[0])
        except SourceAuthError as exc:
            return HealthCheckResult(source_id=SOURCE_ID, status=HealthStatus.AUTHENTICATION_FAILED, message=str(exc))
        except SourceRateLimitError as exc:
            return HealthCheckResult(source_id=SOURCE_ID, status=HealthStatus.RATE_LIMITED, message=str(exc))
        except CollectorError as exc:
            return HealthCheckResult(source_id=SOURCE_ID, status=HealthStatus.UNAVAILABLE, message=str(exc))
        return HealthCheckResult(source_id=SOURCE_ID, status=HealthStatus.HEALTHY, message="OK")
