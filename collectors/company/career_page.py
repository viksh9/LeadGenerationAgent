"""CareerPageCollector — generic, compliant company career-page collector.

Operates against a CareerSourceDefinition. Reuses the shared BaseCollector,
retry/timeout/rate-limit config, hashing, and RawSourceRecord repository. It only
collects job/company/technology/role/location/date/source fields — never personal
data — and never bypasses robots.txt, terms, rate limits, or access controls.

CLI: python -m collectors.company.career_page --source example_company --dry-run
"""

from __future__ import annotations

import argparse
import logging
import time
from datetime import datetime, timedelta, timezone
from typing import Optional
from urllib.parse import urlsplit

import httpx

from collectors.base import BaseCollector, CollectorResult, FetchRequest, HealthCheckResult, HealthStatus
from collectors.company.adapters import CareerAdapter, select_adapter
from collectors.company.config import CareerCollectorConfig, load_career_config
from collectors.company.http_client import CareerCollectorError, RestrictedError, SafeHttpClient
from collectors.company.mapping import job_warnings, map_job
from collectors.company.robots import RobotsPolicy
from collectors.company.sources import (
    CareerSourceDefinition,
    CareerSourceStatus,
    RobotsStatus,
    TermsStatus,
    get_career_registry,
)
from collectors.source_registry import SourceCategory, SourceDefinition, SourceType

logger = logging.getLogger("collectors")


def _is_older(published_at: Optional[datetime], since: datetime) -> bool:
    """True if a (possibly naive) publish date is before `since`. Naive dates are
    treated as UTC so an aware `since` never raises on comparison."""
    if published_at is None:
        return False  # undated jobs are kept (§18)
    pub = published_at if published_at.tzinfo else published_at.replace(tzinfo=timezone.utc)
    cutoff = since if since.tzinfo else since.replace(tzinfo=timezone.utc)
    return pub < cutoff


def _wrap_source(career: CareerSourceDefinition, rpm: int) -> SourceDefinition:
    """A minimal SourceDefinition so BaseCollector's config plumbing is reused."""
    return SourceDefinition(
        source_id=career.source_id,
        name=career.company_name,
        category=SourceCategory.COMPANY,
        source_type=SourceType.PUBLIC_WEB,
        requires_api_key=False,
        supports_pagination=True,
        rate_limit={"requests_per_minute": rpm},
    )


class CareerPageCollector(BaseCollector):
    def __init__(
        self,
        source: CareerSourceDefinition,
        *,
        config: CareerCollectorConfig | None = None,
        client: SafeHttpClient | None = None,
        robots: RobotsPolicy | None = None,
        adapter: CareerAdapter | None = None,
        http: httpx.Client | None = None,
        sleep=time.sleep,
        resolve_hosts: bool = False,
        **kwargs,
    ) -> None:
        self.config = config or load_career_config()
        super().__init__(_wrap_source(source, self.config.requests_per_minute), **kwargs)
        self.career = source
        self._client = client or SafeHttpClient(
            self.config, retry=self.retry, http=http, sleep=sleep, resolve_hosts=resolve_hosts
        )
        self._robots = robots or RobotsPolicy(self._client.try_fetch_text, user_agent=self.config.user_agent)
        self._adapter = adapter or select_adapter(source)

    # -- guards ------------------------------------------------------------- #
    def _ensure_collectable(self) -> None:
        c = self.career
        if not c.career_url:
            raise CareerCollectorError("career source has no career_url")
        if c.requires_js:
            raise CareerCollectorError("page requires JavaScript rendering (NOT_SUPPORTED)")
        if c.terms_status is TermsStatus.RESTRICTED:
            raise RestrictedError("terms status is RESTRICTED — collection not permitted")
        if c.robots_status is RobotsStatus.DISALLOWED:
            raise RestrictedError("robots status is DISALLOWED — collection not permitted")
        live = self._robots.check(c.career_url, source_id=c.source_id)
        if live is RobotsStatus.DISALLOWED:
            raise RestrictedError("robots.txt disallows automated access to this path")

    # -- public API --------------------------------------------------------- #
    def fetch(self, request: FetchRequest | None = None) -> CollectorResult:
        self._ensure_collectable()
        req = request or FetchRequest()
        max_pages = min(req.page or self.config.max_pages, self.config.max_pages)
        max_records = self.config.max_records
        since = req.since

        started = time.monotonic()
        url: Optional[str] = self._adapter.start_url(self.career)
        drafts = []
        warnings: list[str] = []
        errors: list[str] = []
        seen: set[str] = set()
        fetched = skipped = duplicates = pages = 0
        next_url = None

        logger.info("collector_started source_id=%s host=%s", self.career.source_id, urlsplit(url or "").hostname)
        while url and pages < max_pages and len(drafts) < max_records:
            try:
                page = self._client.fetch(url)
            except RestrictedError as exc:
                errors.append(str(exc))
                break
            except CareerCollectorError as exc:
                errors.append(str(exc))
                break
            result = self._adapter.parse(page, self.career)
            pages += 1
            for job in result.jobs:
                fetched += 1
                warnings.extend(job_warnings(job))
                try:
                    draft = map_job(job, self.career, method=result.method)
                except Exception as exc:  # noqa: BLE001 - keep the batch going
                    warnings.append(f"skipped a record: {exc}")
                    continue
                if since and _is_older(draft.published_at, since):
                    skipped += 1
                    continue
                key = draft.external_id or draft.content_hash
                if key in seen:
                    duplicates += 1
                    continue
                seen.add(key)
                drafts.append(draft)
                if len(drafts) >= max_records:
                    break
            next_url = result.next_url
            url = next_url if next_url and next_url not in (page.url,) else None

        duration = round(time.monotonic() - started, 3)
        has_more = bool(next_url) and len(drafts) >= max_records
        logger.info(
            "collector_completed source_id=%s pages=%s fetched=%s accepted=%s duplicates=%s duration=%s",
            self.career.source_id, pages, fetched, len(drafts), duplicates, duration,
        )
        return CollectorResult(
            source_id=self.career.source_id,
            records=drafts,
            page=pages,
            next_cursor=next_url if has_more else None,
            has_more=has_more,
            duration_seconds=duration,
            warnings=warnings,
            errors=errors,
            context={
                "company_name": self.career.company_name,
                "company_domain": self.career.company_domain,
                "pages_fetched": pages,
                "records_fetched": fetched,
                "records_accepted": len(drafts),
                "records_skipped": skipped,
                "duplicates": duplicates,
                "parser_method": self._adapter.name,
            },
        )

    def fetch_incremental(self, request: FetchRequest | None = None) -> CollectorResult:
        """Recency window (lookback_days) + external_id/content_hash dedup.

        Career pages rarely expose reliable incremental cursors, so this filters
        by datePosted when present and otherwise relies on downstream dedup to
        avoid re-storing already-known postings (undated jobs are kept)."""
        req = request or FetchRequest()
        if req.since is None:
            req = req.model_copy(
                update={"since": datetime.now(timezone.utc) - timedelta(days=self.config.lookback_days)}
            )
        return self.fetch(req)

    def health_check(self) -> HealthCheckResult:
        c = self.career
        sid = c.source_id
        if not c.career_url:
            return HealthCheckResult(source_id=sid, status=HealthStatus.NOT_CONFIGURED, message="No career_url configured.")
        if c.requires_js:
            return HealthCheckResult(source_id=sid, status=HealthStatus.DEGRADED, message="Page requires JavaScript (not supported).")
        if c.terms_status is TermsStatus.RESTRICTED or c.robots_status is RobotsStatus.DISALLOWED:
            return HealthCheckResult(source_id=sid, status=HealthStatus.RESTRICTED, message="Collection not permitted (terms/robots).")
        try:
            if self._robots.check(c.career_url, source_id=sid) is RobotsStatus.DISALLOWED:
                return HealthCheckResult(source_id=sid, status=HealthStatus.RESTRICTED, message="robots.txt disallows access.")
            page = self._client.fetch(c.career_url)
        except RestrictedError:
            return HealthCheckResult(source_id=sid, status=HealthStatus.RESTRICTED, message="Access restricted.")
        except (CareerCollectorError, httpx.HTTPError):
            return HealthCheckResult(source_id=sid, status=HealthStatus.UNAVAILABLE, message="Career page not reachable.")
        jobs = self._adapter.parse(page, c).jobs
        if not jobs:
            return HealthCheckResult(source_id=sid, status=HealthStatus.DEGRADED, message="Reachable but no structured jobs found.")
        return HealthCheckResult(source_id=sid, status=HealthStatus.HEALTHY, message="OK")


# --------------------------------------------------------------------------- #
# Development CLI
# --------------------------------------------------------------------------- #
def _source_from_args(args) -> Optional[CareerSourceDefinition]:
    if args.source:
        return get_career_registry().get(args.source)
    if args.url:
        return CareerSourceDefinition(
            source_id="cli",
            company_name="(cli source)",
            career_url=args.url,
            enabled=True,
            terms_status=TermsStatus.ALLOWED,
            robots_status=RobotsStatus.UNKNOWN,
            status=CareerSourceStatus.REQUIRES_REVIEW,
        )
    return None


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    parser = argparse.ArgumentParser(description="Company career-page collector (dev CLI).")
    parser.add_argument("--source", default=None, help="career source_id from config/career_sources.yaml")
    parser.add_argument("--url", default=None, help="ad-hoc public career URL to collect")
    parser.add_argument("--pages", type=int, default=1)
    parser.add_argument("--max-records", type=int, default=25)
    parser.add_argument("--dry-run", action="store_true", help="fetch + parse + summarize, do not persist")
    args = parser.parse_args(argv)

    source = _source_from_args(args)
    if source is None:
        print("Provide --source <id> or --url <career page url>.")
        return 1

    config = load_career_config().model_copy(update={"max_pages": args.pages, "max_records": args.max_records})
    collector = CareerPageCollector(source, config=config, resolve_hosts=True)

    print("Company Career-Page Collector")
    print("-----------------------------\n")
    print(f"Source: {source.source_id}\nCompany: {source.company_name}\nURL: {source.career_url}\n")

    health = collector.health_check()
    print(f"Health: {health.status.value} — {health.message}")
    if health.status in {HealthStatus.NOT_CONFIGURED, HealthStatus.RESTRICTED}:
        return 1

    try:
        result = collector.fetch(FetchRequest(page=args.pages))
    except (CareerCollectorError, RestrictedError) as exc:
        print(f"Collection failed: {exc}")
        return 1

    ctx = result.context
    print(
        f"\nPages fetched: {ctx['pages_fetched']}\nRecords fetched: {ctx['records_fetched']}\n"
        f"Records accepted: {ctx['records_accepted']}\nSkipped (old): {ctx['records_skipped']}\n"
        f"Duplicates: {ctx['duplicates']}\nParser: {ctx['parser_method']}\n"
        f"Warnings: {len(result.warnings)}\nErrors: {len(result.errors)}"
    )

    if args.dry_run:
        print("\n(dry-run — nothing persisted)")
        return 0

    from collectors.service import JobCollectionService
    from config import get_settings
    from database.session import create_session_factory, get_engine, init_db

    settings = get_settings()
    engine = get_engine(settings.database_url)
    init_db(engine)
    with create_session_factory(engine)() as session:
        summary = JobCollectionService(session).collect(collector, [FetchRequest(page=args.pages)])
    print(f"\nPersisted: accepted={summary.accepted} duplicates={summary.skipped_duplicates} errors={len(summary.errors)}")
    return 1 if summary.errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
