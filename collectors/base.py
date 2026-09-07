"""Collector interface + supporting foundations (no network I/O here).

Collectors ONLY collect and return raw source records — they contain no business
scoring/signal logic. Network specifics (rate limiting, retries, timeouts) are
represented as configuration/services so real collectors can reuse them.
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from enum import Enum
from typing import Callable, Optional

from pydantic import BaseModel, ConfigDict, Field

from collectors.raw_record import RawRecordDraft
from collectors.source_registry import SourceDefinition

logger = logging.getLogger("collectors")


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


# --------------------------------------------------------------------------- #
# Network-policy configuration (respected by real collectors; no I/O here)
# --------------------------------------------------------------------------- #
class RateLimitConfig(BaseModel):
    requests_per_minute: Optional[int] = Field(default=None, ge=0)
    requests_per_day: Optional[int] = Field(default=None, ge=0)


class RetryConfig(BaseModel):
    max_attempts: int = Field(default=3, ge=1)
    backoff_base_seconds: float = Field(default=0.5, ge=0)
    backoff_max_seconds: float = Field(default=30.0, ge=0)
    retryable_status_codes: tuple[int, ...] = (429, 500, 502, 503, 504)

    def is_retryable(self, status_code: int) -> bool:
        """Retry only transient statuses — never auth/authorization/4xx (except 429)."""
        return status_code in self.retryable_status_codes

    def backoff_for(self, attempt: int) -> float:
        """Exponential backoff (seconds) for a 1-based attempt number, capped."""
        delay = self.backoff_base_seconds * (2 ** max(0, attempt - 1))
        return min(delay, self.backoff_max_seconds)


class TimeoutConfig(BaseModel):
    connect_timeout: float = Field(default=5.0, gt=0)
    read_timeout: float = Field(default=15.0, gt=0)


class RateLimiter:
    """Minimal in-process limiter: allows N events per rolling window.

    Deterministic and testable via an injectable clock. It records timestamps and
    reports whether another request is currently permitted — it does not sleep.
    """

    def __init__(self, requests_per_minute: Optional[int], *, clock: Callable[[], float] | None = None) -> None:
        self._limit = requests_per_minute
        self._clock = clock or (lambda: _utcnow().timestamp())
        self._events: list[float] = []

    def allow(self) -> bool:
        if not self._limit:
            return True
        now = self._clock()
        self._events = [t for t in self._events if now - t < 60.0]
        if len(self._events) < self._limit:
            self._events.append(now)
            return True
        return False


# --------------------------------------------------------------------------- #
# Requests / results / health
# --------------------------------------------------------------------------- #
class FetchRequest(BaseModel):
    """Parameters a collector may honour, subject to source capabilities."""

    model_config = ConfigDict(extra="forbid")

    query: Optional[str] = None
    since: Optional[datetime] = None
    cursor: Optional[str] = None
    after_external_id: Optional[str] = None
    page: Optional[int] = Field(default=None, ge=1)
    limit: Optional[int] = Field(default=None, ge=1)


class CollectorResult(BaseModel):
    """Structured collector output. Failures surface as warnings/errors, never silently."""

    source_id: str
    fetched_at: datetime = Field(default_factory=_utcnow)
    records: list[RawRecordDraft] = Field(default_factory=list)
    page: Optional[int] = None
    next_cursor: Optional[str] = None
    has_more: bool = False
    total_records: Optional[int] = None
    warnings: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)

    @property
    def records_count(self) -> int:
        return len(self.records)


class HealthStatus(str, Enum):
    HEALTHY = "HEALTHY"
    DEGRADED = "DEGRADED"
    UNAVAILABLE = "UNAVAILABLE"
    NOT_CONFIGURED = "NOT_CONFIGURED"


class HealthCheckResult(BaseModel):
    source_id: str
    status: HealthStatus
    checked_at: datetime = Field(default_factory=_utcnow)
    message: Optional[str] = None  # never contains credentials


# --------------------------------------------------------------------------- #
# Base collector
# --------------------------------------------------------------------------- #
class BaseCollector(ABC):
    """Common interface every real collector implements.

    Collectors return raw records only. `fetch_incremental` defaults to `fetch`
    for sources without incremental support; override where the source allows it.
    """

    def __init__(
        self,
        source: SourceDefinition,
        *,
        rate_limit: RateLimitConfig | None = None,
        retry: RetryConfig | None = None,
        timeout: TimeoutConfig | None = None,
    ) -> None:
        self.source = source
        self.rate_limit = rate_limit or RateLimitConfig(
            requests_per_minute=source.rate_limit.requests_per_minute,
            requests_per_day=source.rate_limit.requests_per_day,
        )
        self.retry = retry or RetryConfig()
        self.timeout = timeout or TimeoutConfig()

    @property
    def source_id(self) -> str:
        return self.source.source_id

    @abstractmethod
    def fetch(self, request: FetchRequest | None = None) -> CollectorResult:
        """Fetch a page/batch of raw records from the source."""

    def fetch_incremental(self, request: FetchRequest | None = None) -> CollectorResult:
        """Incremental fetch. Defaults to `fetch` unless the source supports it."""
        if not self.source.supports_incremental_fetch:
            logger.info("collector_incremental_unsupported source_id=%s", self.source_id)
        return self.fetch(request)

    def health_check(self) -> HealthCheckResult:
        """Report collector readiness. Base implementation reports config state only."""
        if self.source.requires_api_key:
            from collectors.source_registry import source_api_key

            if not source_api_key(self.source_id):
                return HealthCheckResult(
                    source_id=self.source_id,
                    status=HealthStatus.NOT_CONFIGURED,
                    message="API key not configured.",
                )
        return HealthCheckResult(
            source_id=self.source_id,
            status=HealthStatus.NOT_CONFIGURED,
            message="No collector implementation connected yet.",
        )
