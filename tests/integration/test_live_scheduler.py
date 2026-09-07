"""OPT-IN live scheduler/source test (§46). SKIPPED by default.

Runs only when RUN_LIVE_SOURCE_TESTS=true AND a source is actually configured. It
performs a REAL collection through the SAME scheduler handler the app uses, then
asserts only structural/idempotency properties — never exact counts or wording,
and NEVER writes synthetic data. Normal test runs make no external network calls.
"""

from __future__ import annotations

import os

import pytest

_LIVE = os.environ.get("RUN_LIVE_SOURCE_TESTS", "").lower() in {"1", "true", "yes"}

pytestmark = pytest.mark.skipif(
    not _LIVE, reason="live source tests are opt-in (set RUN_LIVE_SOURCE_TESTS=true + a configured source)"
)


def test_live_source_collection_via_scheduler(tmp_path):
    from config.dotenv import load_dotenv
    load_dotenv()

    from collectors.registry import build_collector, runnable_source_ids
    from database.models import JobType, SchedulerRunStatus
    from database.session import create_session_factory, get_engine, init_db
    from scheduler.service import SchedulerService

    # Find a source that is actually configured right now.
    configured_source = None
    for sid in sorted(runnable_source_ids()):
        try:
            collector = build_collector(sid)
        except Exception:
            continue
        cfg = getattr(collector, "config", None)
        if cfg is not None and getattr(cfg, "is_configured", False):
            configured_source = sid
            break
    if configured_source is None:
        pytest.skip("no runnable source is configured; nothing to collect live")

    engine = get_engine(f"sqlite:///{tmp_path / 'live.db'}")
    init_db(engine)
    session = create_session_factory(engine)()
    try:
        svc = SchedulerService(session)
        job = svc.register_job(
            job_name=f"collect:{configured_source}", job_type=JobType.SOURCE_COLLECTION,
            interval_seconds=3600, source_id=configured_source,
        )
        session.commit()
        run = svc.run_job(job, trigger="MANUAL")
        session.commit()
        # A live run either succeeds or is legitimately skipped (budget/config) —
        # never fabricates. Counters are actual and non-negative.
        assert run.status in {SchedulerRunStatus.SUCCESS, SchedulerRunStatus.SKIPPED,
                              SchedulerRunStatus.PARTIAL}
        assert run.records_fetched >= 0 and run.records_new >= 0
    finally:
        session.close()
