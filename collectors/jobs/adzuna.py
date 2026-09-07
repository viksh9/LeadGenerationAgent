"""Adzuna job collector — first real IT job-data integration.

Adzuna API -> RawSourceRecord (via RawRecordDraft). No signal detection or lead
scoring here. Credentials come from the environment (ADZUNA_APP_ID / ADZUNA_APP_KEY)
and are never logged. Use the official documented API only — no page scraping.

CLI:  python -m collectors.jobs.adzuna --query "Java Developer" --location Bengaluru --pages 1 --dry-run
"""

from __future__ import annotations

import argparse
import logging
import time
from datetime import datetime, timezone
from typing import Optional

import httpx

from collectors.base import BaseCollector, CollectorResult, FetchRequest, HealthCheckResult, HealthStatus
from collectors.jobs.client import (
    AdzunaClient,
    CollectorError,
    SourceAuthError,
    SourceRateLimitError,
)
from collectors.jobs.config import AdzunaConfig, load_adzuna_config
from collectors.jobs.mapping import is_it_relevant, job_warnings, map_job
from collectors.source_registry import SourceDefinition, get_registry

logger = logging.getLogger("collectors")

MAX_RESULTS_PER_PAGE = 50


class AdzunaJobCollector(BaseCollector):
    def __init__(
        self,
        source: SourceDefinition,
        *,
        config: AdzunaConfig | None = None,
        client: AdzunaClient | None = None,
        http: httpx.Client | None = None,
        sleep=time.sleep,
        **kwargs,
    ) -> None:
        super().__init__(source, **kwargs)
        self.config = config or load_adzuna_config()
        self._client = client or AdzunaClient(
            self.config, retry=self.retry, timeout=self.timeout, http=http, sleep=sleep
        )

    # -- public API --------------------------------------------------------- #
    def fetch(self, request: FetchRequest | None = None) -> CollectorResult:
        if not self.config.is_configured:
            raise CollectorError("Adzuna is not configured (missing ADZUNA_APP_ID / ADZUNA_APP_KEY).")
        req = request or FetchRequest()
        query = req.query or (self.config.search_terms[0] if self.config.search_terms else "software engineer")
        page = req.page or 1
        per_page = min(req.limit or self.config.results_per_page, MAX_RESULTS_PER_PAGE)

        params: dict[str, object] = {
            "results_per_page": per_page,
            "what": query,
            "content-type": "application/json",
            "sort_by": "date",
        }
        if req.location:
            params["where"] = req.location
        # Recency window: explicit `since`, else the configured lookback.
        days = (datetime.now(timezone.utc) - req.since).days if req.since else self.config.lookback_days
        if days and days > 0:
            params["max_days_old"] = max(0, days)

        started = time.monotonic()
        logger.info("collector_started source_id=adzuna query=%r country=%s page=%s", query, self.config.country, page)
        payload = self._client.search(country=self.config.country, page=page, params=params)

        items = payload.get("results", []) or []
        records = []
        warnings: list[str] = []
        skipped_non_it = 0
        for item in items:
            if not is_it_relevant(item):
                skipped_non_it += 1
                continue
            warnings.extend(job_warnings(item))
            try:
                records.append(map_job(item, country=self.config.country, query=query, location=req.location))
            except Exception as exc:  # noqa: BLE001 - keep the batch going
                warnings.append(f"skipped a record: {exc}")

        if skipped_non_it:
            warnings.append(f"filtered {skipped_non_it} non-IT record(s)")

        total = payload.get("count")
        has_more = bool(total is not None and page * per_page < total)
        duration = round(time.monotonic() - started, 3)
        logger.info(
            "page_completed source_id=adzuna query=%r page=%s records_count=%s duration=%s",
            query, page, len(records), duration,
        )
        logger.info("collector_completed source_id=adzuna query=%r records_count=%s", query, len(records))
        return CollectorResult(
            source_id="adzuna",
            records=records,
            page=page,
            next_cursor=str(page + 1) if has_more else None,
            has_more=has_more,
            total_records=total,
            duration_seconds=duration,
            context={"query": query, "country": self.config.country, "location": req.location},
            warnings=warnings,
        )

    def fetch_incremental(self, request: FetchRequest | None = None) -> CollectorResult:
        """Adzuna has no true cursor; use the recency window (max_days_old) and rely
        on external_id/content_hash dedup downstream to skip already-known jobs."""
        req = request or FetchRequest()
        if req.since is None:
            from datetime import timedelta

            req = req.model_copy(
                update={"since": datetime.now(timezone.utc) - timedelta(days=self.config.lookback_days)}
            )
        return self.fetch(req)

    def health_check(self) -> HealthCheckResult:
        if not self.config.is_configured:
            return HealthCheckResult(
                source_id="adzuna",
                status=HealthStatus.NOT_CONFIGURED,
                message="ADZUNA_APP_ID / ADZUNA_APP_KEY not configured.",
            )
        try:
            self._client.search(
                country=self.config.country,
                page=1,
                params={"results_per_page": 1, "content-type": "application/json"},
            )
        except SourceAuthError as exc:
            return HealthCheckResult(source_id="adzuna", status=HealthStatus.AUTHENTICATION_FAILED, message=str(exc))
        except SourceRateLimitError as exc:
            return HealthCheckResult(source_id="adzuna", status=HealthStatus.RATE_LIMITED, message=str(exc))
        except CollectorError as exc:
            return HealthCheckResult(source_id="adzuna", status=HealthStatus.UNAVAILABLE, message=str(exc))
        return HealthCheckResult(source_id="adzuna", status=HealthStatus.HEALTHY, message="OK")

    def plan_requests(
        self, *, max_pages: Optional[int] = None,
        mode: Optional[str] = None, max_requests: Optional[int] = None,
    ) -> list[FetchRequest]:
        """Build a bounded IT search plan using the configured query strategy.

        Uses the controlled ROLE_FIRST / TECHNOLOGY_FIRST / LOCATION_FIRST strategy
        (India-wide per term by default) capped at ``max_requests_per_run`` — never
        the old blind roles×locations×pages cartesian.
        """
        from collectors.jobs.query_strategy import build_plan

        return build_plan(
            mode=mode or self.config.search_mode,
            search_terms=self.config.search_terms,
            locations=self.config.locations,
            max_pages=max_pages or self.config.max_pages,
            max_requests=max_requests or self.config.max_requests_per_run,
        )


# --------------------------------------------------------------------------- #
# Development CLI
# --------------------------------------------------------------------------- #
def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    parser = argparse.ArgumentParser(description="Adzuna IT job collector (dev CLI).")
    parser.add_argument("--query", default="Java Developer")
    parser.add_argument("--location", default=None)
    parser.add_argument("--pages", type=int, default=1)
    parser.add_argument("--results-per-page", type=int, default=5)
    parser.add_argument("--dry-run", action="store_true", help="Fetch + summarize but do not persist.")
    args = parser.parse_args(argv)

    source = get_registry().get("adzuna")
    collector = AdzunaJobCollector(source)
    health = collector.health_check()
    if health.status == HealthStatus.NOT_CONFIGURED:
        print("Adzuna is not configured. Set ADZUNA_APP_ID and ADZUNA_APP_KEY.")
        return 1

    from collectors.service import JobCollectionService
    from config import get_settings
    from database.session import create_session_factory, get_engine, init_db

    country_label = {"in": "India", "gb": "United Kingdom", "us": "United States"}.get(
        collector.config.country, collector.config.country
    )
    requests = [FetchRequest(query=args.query, location=args.location, page=p) for p in range(1, args.pages + 1)]

    print("Adzuna Collector")
    print("----------------\n")
    print(f"Source: Adzuna\nCountry: {country_label}\nQuery: {args.query}\nLocation: {args.location or 'Any'}\n")

    if args.dry_run:
        fetched = it_relevant = warnings = 0
        for req in requests:
            result = collector.fetch(req.model_copy(update={"limit": args.results_per_page}))
            fetched += result.records_count
            it_relevant += result.records_count
            warnings += len(result.warnings)
        print(f"Records fetched: {fetched}\nIT-relevant: {it_relevant}\nWarnings: {warnings}\nErrors: 0")
        print("\n(dry-run — nothing persisted)")
        return 0

    settings = get_settings()
    engine = get_engine(settings.database_url)
    init_db(engine)
    with create_session_factory(engine)() as session:
        service = JobCollectionService(session)
        summary = service.collect(
            collector,
            [r.model_copy(update={"limit": args.results_per_page}) for r in requests],
        )
    print(
        f"Records fetched: {summary.fetched}\nRecords accepted: {summary.accepted}\n"
        f"Duplicates: {summary.skipped_duplicates}\nWarnings: {len(summary.warnings)}\nErrors: {len(summary.errors)}"
    )
    return 1 if summary.errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
