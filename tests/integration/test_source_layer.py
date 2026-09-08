"""Source-layer tests (Prompt 46 §35, §48, §50, §53).

Offline: no external network. Verifies the orchestrator's honest status handling
and failure isolation, the source-readiness audit, and that unconfigured/manual
sources never fabricate data. Job collection against a live provider is exercised
with an injected fake collector (no network).
"""

from __future__ import annotations

import pytest

from app.report import source_readiness
from collectors.orchestrator import SourceOrchestrator


def test_unconfigured_source_reports_not_configured(seed_session):
    # Jooble has no credentials in the test env → NOT_CONFIGURED, nothing collected.
    res = SourceOrchestrator(seed_session).collect_source("jooble", dry_run=True)
    assert res.status == "NOT_CONFIGURED"
    assert res.records_received == 0 and res.records_persisted == 0


def test_government_source_is_manual(seed_session):
    res = SourceOrchestrator(seed_session).collect_source("government_procurement", dry_run=True)
    assert res.status == "MANUAL_SOURCE_REQUIRED"
    assert res.records_received == 0


def test_news_source_without_feed_is_not_configured(seed_session):
    res = SourceOrchestrator(seed_session).collect_source("rss_news", dry_run=True)
    assert res.status == "NOT_CONFIGURED"


def test_unknown_source_not_implemented(seed_session):
    res = SourceOrchestrator(seed_session).collect_source("does_not_exist", dry_run=True)
    assert res.status in ("NOT_IMPLEMENTED", "ERROR")
    assert res.records_persisted == 0


def test_failure_isolation_across_sources(seed_session, monkeypatch):
    """One source raising must not stop the others (§35)."""
    orch = SourceOrchestrator(seed_session)
    real_collect = orch._collect_jobs

    def flaky(source_id, category, **kw):
        if source_id == "adzuna":
            raise RuntimeError("boom")   # simulate a provider blowing up
        return real_collect(source_id, category, **kw)

    monkeypatch.setattr(orch, "_collect_jobs", flaky)
    results = orch.run(["adzuna", "jooble", "government_procurement"], dry_run=True)
    by_id = {r.source_id: r.status for r in results}
    assert by_id["adzuna"] == "ERROR"                     # isolated failure
    assert by_id["jooble"] == "NOT_CONFIGURED"            # still evaluated
    assert by_id["government_procurement"] == "MANUAL_SOURCE_REQUIRED"
    assert len(results) == 3


def test_no_fabrication_on_failure(seed_session, monkeypatch):
    orch = SourceOrchestrator(seed_session)
    monkeypatch.setattr(orch, "_collect_jobs",
                        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("down")))
    res = orch.collect_source("adzuna", dry_run=True)
    assert res.status == "ERROR"
    assert res.records_received == 0 and res.records_persisted == 0   # no fake data


# --------------------------------------------------------------------------- #
# source-readiness audit
# --------------------------------------------------------------------------- #
def test_source_readiness_truthful(seed_session):
    report = source_readiness(seed_session)
    assert report["total"] >= 4
    verdicts = {r["source_id"]: r["verdict"] for r in report["sources"]}
    # Nothing is CONNECTED/LIVE_VERIFIED without a real recorded success in this DB.
    assert verdicts.get("jooble") in ("NOT_CONFIGURED", "REQUIRES_REVIEW")
    assert verdicts.get("government_open_data") in ("NOT_IMPLEMENTED", "NOT_CONFIGURED")
    # Every row carries a licensing-review flag (never silently assumed unrestricted).
    assert all("requires_license_review" in r for r in report["sources"])


# --------------------------------------------------------------------------- #
# CLI dispatch (offline)
# --------------------------------------------------------------------------- #
def test_collectors_cli_list_runs():
    from app.collectors import main
    assert main(["list"]) == 0


def test_collectors_cli_run_unconfigured_returns_not_configured_code():
    from app.collectors import main
    # jooble is unconfigured → exit code 2 (NOT_CONFIGURED); no network for a dry-run
    # of an unconfigured source (the config gate short-circuits before any request).
    assert main(["run", "--source", "jooble", "--dry-run"]) == 2
