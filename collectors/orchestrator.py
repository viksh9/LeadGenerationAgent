"""SourceOrchestrator (Prompt 46 §28, §35).

Runs one or more real sources through the SAME collector/pipeline services the
rest of the app uses — no duplicate ingestion logic. Each source is isolated: one
source failing (auth, rate-limit, error) never stops the others. Nothing is ever
fabricated on failure (§50): a source that is unconfigured/unavailable simply
reports its honest status and collects nothing. Persistence happens only when
explicitly requested (persist=True); the default is a safe dry-run.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from datetime import datetime

from sqlalchemy.orm import Session

from database.models import DataProvenance, utcnow

logger = logging.getLogger(__name__)

# Sources with no permitted public API — collection is manual (§10).
_MANUAL_SOURCES = {"government_procurement", "government_open_data", "project_registry"}
# News/announcement sources use the business-signal collector + a permitted feed URL.
_NEWS_SOURCES = {"rss_news", "company_newsroom"}


@dataclass
class SourceRunResult:
    source_id: str
    category: str
    status: str                      # COLLECTED | DRY_RUN_OK | NOT_CONFIGURED | NOT_IMPLEMENTED |
                                     # MANUAL_SOURCE_REQUIRED | AUTH_FAILED | TRANSIENT_FAILURE |
                                     # ERROR | BUDGET_EXHAUSTED | SKIPPED
    persisted: bool = False
    records_received: int = 0
    records_persisted: int = 0
    duplicates: int = 0
    duration_ms: int = 0
    detail: str | None = None

    def as_dict(self) -> dict:
        return {
            "source_id": self.source_id, "category": self.category, "status": self.status,
            "persisted": self.persisted, "records_received": self.records_received,
            "records_persisted": self.records_persisted, "duplicates": self.duplicates,
            "duration_ms": self.duration_ms, "detail": self.detail,
        }


class SourceOrchestrator:
    def __init__(self, session: Session):
        self.session = session

    def _category(self, source_id: str) -> str:
        try:
            from collectors.source_registry import get_registry
            defn = get_registry().get(source_id)
            return getattr(defn.category, "value", str(defn.category)) if defn else "OTHER"
        except Exception:
            return "OTHER"

    def collect_source(self, source_id: str, *, dry_run: bool = True, persist: bool = False,
                       max_records: int = 50, now: datetime | None = None) -> SourceRunResult:
        """Collect one source with full failure isolation. Never raises."""
        now = now or utcnow()
        category = self._category(source_id)
        started = time.monotonic()
        persist = persist and not dry_run
        try:
            if source_id in _MANUAL_SOURCES:
                return SourceRunResult(source_id, category, "MANUAL_SOURCE_REQUIRED",
                                       detail="No permitted public API; manual import only "
                                              "(scripts/import_tender.py). Anti-bot protections are never bypassed.")
            if source_id in _NEWS_SOURCES:
                return self._collect_news(source_id, category, dry_run=dry_run, persist=persist, now=now)
            return self._collect_jobs(source_id, category, dry_run=dry_run, persist=persist,
                                      max_records=max_records, now=now)
        except Exception as exc:  # noqa: BLE001 — isolation: never propagate
            logger.warning("orchestrator: %s failed: %s", source_id, type(exc).__name__)
            return SourceRunResult(source_id, category, "ERROR",
                                   detail=f"{type(exc).__name__}: {exc}"[:300],
                                   duration_ms=int((time.monotonic() - started) * 1000))
        finally:
            pass

    def _collect_jobs(self, source_id, category, *, dry_run, persist, max_records, now) -> SourceRunResult:
        from collectors.base import FetchRequest
        from collectors.errors import (
            CollectorError, SourceAuthError, SourceRateLimitError, SourceUnavailableError,
        )
        from collectors.registry import CollectorNotImplemented, build_collector, is_runnable
        from collectors.service import JobCollectionService
        from collectors.source_budget import get_state as get_budget_state
        from collectors.source_budget import record_usage as record_budget_usage
        from ingestion.job_pipeline import run_company_pipeline

        started = time.monotonic()
        if not is_runnable(source_id):
            return SourceRunResult(source_id, category, "NOT_IMPLEMENTED",
                                   detail="No runnable global collector (per-company/manual source).")
        try:
            collector = build_collector(source_id)
        except CollectorNotImplemented:
            return SourceRunResult(source_id, category, "NOT_IMPLEMENTED", detail="collector not implemented")
        except CollectorError as exc:
            return SourceRunResult(source_id, category, "ERROR", detail=str(exc)[:200])

        config = getattr(collector, "config", None)
        if config is not None and hasattr(config, "is_configured") and not config.is_configured:
            return SourceRunResult(source_id, category, "NOT_CONFIGURED",
                                   detail="credentials/board not configured; nothing collected")

        # Plan requests (reuse collector planners where available).
        reqs = self._plan(collector, max_records)

        # Lifetime budget guard (e.g. Jooble 500).
        budget_limit = getattr(config, "lifetime_request_budget", None) if config is not None else None
        if budget_limit:
            state = get_budget_state(self.session, source_id, budget=budget_limit)
            if state.exhausted:
                return SourceRunResult(source_id, category, "BUDGET_EXHAUSTED",
                                       detail=f"lifetime request budget ({budget_limit}) exhausted")
            reqs = reqs[: max(0, state.remaining)]
            if not reqs:
                return SourceRunResult(source_id, category, "BUDGET_EXHAUSTED", detail="no remaining budget")

        svc = JobCollectionService(self.session)
        try:
            summary = svc.collect(collector, reqs, dry_run=(not persist), record_run=persist)
        except SourceAuthError as exc:
            return SourceRunResult(source_id, category, "AUTH_FAILED", detail=str(exc)[:200])
        except (SourceRateLimitError, SourceUnavailableError) as exc:
            return SourceRunResult(source_id, category, "TRANSIENT_FAILURE", detail=str(exc)[:200])

        received = summary.fetched
        persisted = 0
        if persist:
            record_budget_usage_local = budget_limit and record_budget_usage(
                self.session, source_id, summary.requests, budget=budget_limit)
            run_company_pipeline(self.session, provenance=DataProvenance.REAL, now=now)
            persisted = summary.accepted
        dur = int((time.monotonic() - started) * 1000)
        return SourceRunResult(
            source_id, category, "COLLECTED" if persist else "DRY_RUN_OK", persisted=persist,
            records_received=received, records_persisted=persisted,
            duplicates=summary.skipped_duplicates, duration_ms=dur,
            detail=(f"fetched {received}; persisted {persisted}" if persist
                    else f"fetched {received}; nothing persisted (dry-run)"),
        )

    def _collect_news(self, source_id, category, *, dry_run, persist, now) -> SourceRunResult:
        from collectors.source_registry import get_registry
        defn = get_registry().get(source_id)
        feed_url = defn.base_url if defn else None
        if not feed_url:
            return SourceRunResult(source_id, category, "NOT_CONFIGURED",
                                   detail="no permitted feed URL configured; nothing collected")
        # A feed is configured: use the business-signal collector (robots-checked,
        # SSRF-safe) then the business pipeline. Persist only when requested.
        from collectors.base import FetchRequest
        from collectors.business.collector import BusinessSignalCollector
        from collectors.business.config import load_business_config
        from ingestion.business_pipeline import run_business_pipeline

        started = time.monotonic()
        collector = BusinessSignalCollector(defn, config=load_business_config())
        result = collector.fetch(FetchRequest(cursor=feed_url))
        received = len(result.records or [])
        persisted = 0
        if persist:
            from collectors.service import JobCollectionService  # reuse raw persistence
            summary = JobCollectionService(self.session).collect(collector, [FetchRequest(cursor=feed_url)],
                                                                 record_run=True)
            run_business_pipeline(self.session, provenance=DataProvenance.REAL, now=now)
            persisted = summary.accepted
            received = summary.fetched
        return SourceRunResult(
            source_id, category, "COLLECTED" if persist else "DRY_RUN_OK", persisted=persist,
            records_received=received, records_persisted=persisted,
            duration_ms=int((time.monotonic() - started) * 1000),
            detail=(f"fetched {received}; persisted {persisted}" if persist
                    else f"fetched {received}; nothing persisted (dry-run)"),
        )

    def _plan(self, collector, max_records: int) -> list:
        from collectors.base import FetchRequest
        import inspect
        if hasattr(collector, "plan_requests"):
            try:
                params = inspect.signature(collector.plan_requests).parameters
                kwargs = {}
                if "max_pages" in params:
                    kwargs["max_pages"] = 1
                if "max_requests" in params:
                    kwargs["max_requests"] = 1
                plan = list(collector.plan_requests(**kwargs))
                if plan:
                    return plan
            except Exception:
                pass
        return [FetchRequest(page=1, limit=max_records)]

    def run(self, source_ids: list[str], *, dry_run: bool = True, persist: bool = False,
            max_records: int = 50, now: datetime | None = None) -> list[SourceRunResult]:
        """Run several sources with per-source isolation (§35). Returns all results."""
        now = now or utcnow()
        results: list[SourceRunResult] = []
        for sid in source_ids:
            results.append(self.collect_source(sid, dry_run=dry_run, persist=persist,
                                               max_records=max_records, now=now))
        return results
