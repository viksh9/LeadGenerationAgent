"""BusinessSignalCollector — collect IT-business signals from permitted feeds.

Reuses the shared safe HTTP client (SSRF/size/redirect/content-type guards),
robots policy, and retries — no second networking implementation. Produces raw
NEWS records (record_type NEWS_ARTICLE) with a detected classification in the
payload; normalization into BusinessSignals happens downstream.
"""

from __future__ import annotations

import logging
import time
from datetime import datetime, timedelta, timezone
from typing import Optional

import httpx

from collectors.base import BaseCollector, CollectorResult, FetchRequest, HealthCheckResult, HealthStatus
from collectors.business.config import load_business_config
from collectors.business.feed import parse_feed
from collectors.company.http_client import CareerCollectorError, RestrictedError, SafeHttpClient
from collectors.company.robots import RobotsPolicy
from collectors.company.sources import RobotsStatus
from collectors.raw_record import RawRecordDraft
from collectors.source_registry import SourceDefinition
from intelligence.business_signal_detector import BusinessSignalDetector

logger = logging.getLogger("collectors")


class BusinessSignalCollector(BaseCollector):
    def __init__(
        self,
        source: SourceDefinition,
        *,
        config=None,
        feed_url: Optional[str] = None,
        client: SafeHttpClient | None = None,
        robots: RobotsPolicy | None = None,
        http: httpx.Client | None = None,
        sleep=time.sleep,
        resolve_hosts: bool = False,
        detector: BusinessSignalDetector | None = None,
        **kwargs,
    ) -> None:
        super().__init__(source, **kwargs)
        self.config = config or load_business_config()
        self.feed_url = feed_url or source.base_url
        self._client = client or SafeHttpClient(
            self.config, retry=self.retry, http=http, sleep=sleep, resolve_hosts=resolve_hosts
        )
        self._robots = robots or RobotsPolicy(self._client.try_fetch_text, user_agent=self.config.user_agent)
        self._detector = detector or BusinessSignalDetector()

    def _ensure_ready(self) -> str:
        if not self.feed_url:
            raise CareerCollectorError("business source has no feed URL configured")
        if self._robots.check(self.feed_url, source_id=self.source_id) is RobotsStatus.DISALLOWED:
            raise RestrictedError("robots.txt disallows automated access to this feed")
        return self.feed_url

    def fetch(self, request: FetchRequest | None = None) -> CollectorResult:
        req = request or FetchRequest()
        url = req.cursor or self._ensure_ready()
        if req.cursor:  # ad-hoc URL still gets a robots check
            if self._robots.check(url, source_id=self.source_id) is RobotsStatus.DISALLOWED:
                raise RestrictedError("robots.txt disallows automated access to this feed")

        since = req.since or (datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=self.config.lookback_days))
        if since.tzinfo:
            since = since.astimezone(timezone.utc).replace(tzinfo=None)
        query = (req.query or "").lower()
        limit = min(req.limit or self.config.max_records, self.config.max_records)

        started = time.monotonic()
        page = self._client.fetch(url)
        items = parse_feed(page.text)
        records: list[RawRecordDraft] = []
        warnings: list[str] = []
        skipped_irrelevant = skipped_old = 0

        for item in items:
            if query and query not in f"{item.title or ''} {item.summary or ''}".lower():
                continue
            if item.published_at and item.published_at < since:
                skipped_old += 1
                continue
            detected = self._detector.detect(item.title, item.summary)
            if not detected.is_relevant:
                skipped_irrelevant += 1
                continue
            if not item.title:
                warnings.append("feed item missing title")
            records.append(RawRecordDraft(
                source_id=self.source_id,
                external_id=item.guid or item.link,
                source_url=item.link,
                published_at=item.published_at,
                record_type="NEWS_ARTICLE",
                title=item.title,
                description=item.summary,
                company_name=item.company_name,
                technologies=detected.technologies,
                industry=None,
                raw_payload={
                    "source": "business-feed",
                    "detected_signal_type": detected.signal_type.value,
                    "detected_strength": detected.signal_strength.value,
                    "detected_keywords": detected.detected_keywords,
                    "project_value": detected.project_value,
                    "currency": detected.currency,
                    "project_value_text": detected.project_value_text,
                },
                is_synthetic=False,
            ))
            if len(records) >= limit:
                break

        if skipped_irrelevant:
            warnings.append(f"filtered {skipped_irrelevant} non-IT-business item(s)")
        duration = round(time.monotonic() - started, 3)
        logger.info(
            "business_collect source_id=%s fetched=%s relevant=%s skipped_old=%s",
            self.source_id, len(items), len(records), skipped_old,
        )
        return CollectorResult(
            source_id=self.source_id,
            records=records,
            duration_seconds=duration,
            warnings=warnings,
            context={
                "feed_items": len(items),
                "records_accepted": len(records),
                "skipped_irrelevant": skipped_irrelevant,
                "skipped_old": skipped_old,
            },
        )

    def health_check(self) -> HealthCheckResult:
        sid = self.source_id
        if not self.feed_url:
            return HealthCheckResult(source_id=sid, status=HealthStatus.NOT_CONFIGURED, message="No feed URL configured.")
        try:
            if self._robots.check(self.feed_url, source_id=sid) is RobotsStatus.DISALLOWED:
                return HealthCheckResult(source_id=sid, status=HealthStatus.RESTRICTED, message="robots.txt disallows access.")
            page = self._client.fetch(self.feed_url)
        except RestrictedError:
            return HealthCheckResult(source_id=sid, status=HealthStatus.RESTRICTED, message="Access restricted.")
        except (CareerCollectorError, httpx.HTTPError):
            return HealthCheckResult(source_id=sid, status=HealthStatus.UNAVAILABLE, message="Feed not reachable.")
        if not parse_feed(page.text):
            return HealthCheckResult(source_id=sid, status=HealthStatus.DEGRADED, message="Reachable but no parseable feed items.")
        return HealthCheckResult(source_id=sid, status=HealthStatus.HEALTHY, message="OK")
