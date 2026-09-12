"""Integration tests for the monitoring & scheduling layer (§45).

Covers the real-data drivers, notification service (dedup/severity/preferences/
lifecycle), scheduler (register/due/run/idempotency/lock/retry/audit/pause/
resume), reprocessing + AI trigger gate, and the APIs. All offline: no external
network. Records are built directly in a throwaway DB (test fixtures only — never
the app DB).
"""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest

import api.main
from api.dependencies import get_session
from database.models import (
    Alert,
    AlertSeverity,
    AlertStatus,
    AlertType,
    Company,
    CompanyChangeEvent,
    DataProvenance,
    JobChangeEvent,
    JobRecord,
    JobStatus,
    JobType,
    Lead,
    LeadPriority,
    ScheduledJobStatus,
    SchedulerRunStatus,
    SourceHealth,
    SourceConnectionStatus,
    TenderRecord,
    TenderStatus,
    VerificationStatus,
)
from monitoring.findings import Finding
from notifications.preferences import get_or_create_preferences, update_preferences
from notifications.service import NotificationService
from scheduler.errors import PermanentJobError, TransientJobError
from scheduler.reprocess import run_monitoring_cycle
from scheduler.service import SchedulerService

NOW = datetime(2026, 9, 7, 12, 0, 0)


# --------------------------------------------------------------------------- #
# Helpers to seed REAL-shaped records into the throwaway DB.
# --------------------------------------------------------------------------- #
def _company(session, name="Acme Tech"):
    c = Company(canonical_name=name, normalized_name=name.lower(), data_provenance=DataProvenance.REAL)
    session.add(c)
    session.flush()
    return c


def _job(session, i, when, techs=("java",), status=JobStatus.ACTIVE, company="Acme Tech"):
    j = JobRecord(
        content_hash=f"h{i}", canonical_key=f"k{i}", company_name=company,
        normalized_company_name=company.lower(), normalized_title=f"Engineer {i}",
        technologies=list(techs), job_status=status, data_provenance=DataProvenance.REAL,
        first_seen_at=when, last_seen_at=when, published_at=when,
    )
    session.add(j)
    return j


def _seed_surge(session, now=NOW):
    _company(session)
    prev = now - timedelta(days=45)
    cur = now - timedelta(days=5)
    for i in range(5):
        _job(session, 1000 + i, prev, techs=("java",))
    for i in range(18):
        _job(session, 2000 + i, cur, techs=("aws", "java"))
    session.flush()


# --------------------------------------------------------------------------- #
# Change-detection driver
# --------------------------------------------------------------------------- #
def test_detect_new_jobs_from_real_records(seed_session):
    _seed_surge(seed_session)
    from monitoring.change_detection import detect_job_changes
    run_since = NOW - timedelta(days=10)
    summary = detect_job_changes(seed_session, now=NOW, run_since=run_since)
    assert summary.new == 18                      # only the current-period jobs are NEW
    assert summary.removed == 5                    # older jobs not seen this cycle → REMOVED_FROM_SOURCE
    assert seed_session.query(JobChangeEvent).count() == 23


def test_job_change_idempotent(seed_session):
    _seed_surge(seed_session)
    from monitoring.change_detection import detect_job_changes
    run_since = NOW - timedelta(days=10)
    detect_job_changes(seed_session, now=NOW, run_since=run_since)
    first = seed_session.query(JobChangeEvent).count()
    detect_job_changes(seed_session, now=NOW, run_since=run_since)
    assert seed_session.query(JobChangeEvent).count() == first   # no duplicates (§21)


# --------------------------------------------------------------------------- #
# Monitoring cycle: surge + company change + alerts
# --------------------------------------------------------------------------- #
def test_monitoring_cycle_detects_hiring_surge(seed_session):
    _seed_surge(seed_session)
    res = run_monitoring_cycle(seed_session, now=NOW, run_since=NOW - timedelta(days=10))
    types = {a.alert_type for a in seed_session.query(Alert).all()}
    assert AlertType.HIRING_SURGE in types
    assert any(e.change_type == "HIRING_ACTIVITY_INCREASED"
               for e in seed_session.query(CompanyChangeEvent).all())
    assert res.alerts_created >= 1


def test_monitoring_cycle_idempotent(seed_session):
    _seed_surge(seed_session)
    run_monitoring_cycle(seed_session, now=NOW, run_since=NOW - timedelta(days=10))
    before = seed_session.query(Alert).count()
    run_monitoring_cycle(seed_session, now=NOW, run_since=NOW - timedelta(days=10))
    assert seed_session.query(Alert).count() == before   # dedup (§28)


# --------------------------------------------------------------------------- #
# Tender monitoring
# --------------------------------------------------------------------------- #
def _tender(session, closing_in_days, status=TenderStatus.OPEN, now=NOW, sid="T1"):
    t = TenderRecord(
        source_id="cppp", source_record_id=sid, content_hash=f"th{sid}", title="IT services RFP",
        organization_name="Gov Dept", closing_date=now + timedelta(days=closing_in_days),
        tender_status=status, data_provenance=DataProvenance.REAL, first_seen_at=now, last_seen_at=now,
    )
    session.add(t)
    session.flush()
    return t


def test_tender_closing_soon_alert(seed_session):
    _tender(seed_session, closing_in_days=3)
    from monitoring.tenders import detect_closing_soon
    findings = detect_closing_soon(seed_session, now=NOW)
    assert any(f.alert_type is AlertType.TENDER_CLOSING_SOON for f in findings)


def test_cancelled_tender_never_alerts(seed_session):
    _tender(seed_session, closing_in_days=3, status=TenderStatus.CANCELLED)
    from monitoring.tenders import detect_closing_soon
    assert detect_closing_soon(seed_session, now=NOW) == []


def test_new_tender_detected(seed_session):
    _tender(seed_session, closing_in_days=30, sid="T-new")
    from monitoring.tenders import detect_new_tenders
    findings = detect_new_tenders(seed_session, now=NOW, run_since=NOW - timedelta(days=1))
    assert any(f.alert_type is AlertType.NEW_TENDER for f in findings)


# --------------------------------------------------------------------------- #
# Source-health scan idempotency (§20)
# --------------------------------------------------------------------------- #
def test_source_health_scan_emits_once_per_transition(seed_session):
    seed_session.add(SourceHealth(source_id="adzuna",
                                  connection_status=SourceConnectionStatus.ERROR,
                                  last_failure_at=NOW))
    seed_session.flush()
    from monitoring.source_health import scan_source_health
    s1 = scan_source_health(seed_session, now=NOW)
    assert len(s1.events) == 1
    s2 = scan_source_health(seed_session, now=NOW)
    assert len(s2.events) == 0     # no duplicate recovery/failure on re-scan (§20)


# --------------------------------------------------------------------------- #
# NotificationService: severity / preferences / dedup / lifecycle
# --------------------------------------------------------------------------- #
def _finding(**over):
    base = dict(alert_type=AlertType.HIRING_SURGE, title="t", message="m",
                dedup_key="k1", severity=AlertSeverity.HIGH, company_id=1)
    base.update(over)
    return Finding(**base)


def test_alert_dedup(seed_session):
    svc = NotificationService(seed_session)
    svc.emit([_finding(dedup_key="dk")], now=NOW)
    r = svc.emit([_finding(dedup_key="dk")], now=NOW)
    assert r.skipped_duplicate == 1 and seed_session.query(Alert).count() == 1


def test_alert_min_severity_preference(seed_session):
    update_preferences(seed_session, min_severity=AlertSeverity.HIGH.value)
    svc = NotificationService(seed_session)
    r = svc.emit([_finding(dedup_key="low", severity=AlertSeverity.LOW,
                           alert_type=AlertType.HIRING_SURGE)], now=NOW)
    assert r.created_count == 0 and r.skipped_preference == 1


def test_alert_disabled_type_preference(seed_session):
    update_preferences(seed_session, enabled_alert_types=["NEW_TENDER"])
    svc = NotificationService(seed_session)
    r = svc.emit([_finding(alert_type=AlertType.HIRING_SURGE, dedup_key="x")], now=NOW)
    assert r.created_count == 0 and r.skipped_preference == 1


def test_business_alert_requires_real_provenance(seed_session):
    svc = NotificationService(seed_session)
    r = svc.emit([_finding(dedup_key="syn", provenance="SYNTHETIC")], now=NOW)
    assert r.created_count == 0 and r.skipped_provenance == 1   # §33


def test_operational_alert_allowed_without_real_flag(seed_session):
    svc = NotificationService(seed_session)
    r = svc.emit([_finding(alert_type=AlertType.SOURCE_FAILURE, dedup_key="op",
                           provenance="OPERATIONAL", severity=AlertSeverity.MEDIUM)], now=NOW)
    assert r.created_count == 1


def test_alert_lifecycle(seed_session):
    svc = NotificationService(seed_session)
    svc.emit([_finding(dedup_key="lc")], now=NOW)
    alert = seed_session.query(Alert).first()
    assert svc.unread_count() == 1
    svc.set_status(alert.id, AlertStatus.ACKNOWLEDGED, now=NOW)
    assert alert.status is AlertStatus.ACKNOWLEDGED and alert.acknowledged_at is not None
    assert svc.unread_count() == 0


# --------------------------------------------------------------------------- #
# Scheduler service
# --------------------------------------------------------------------------- #
def test_scheduler_register_and_due(seed_session):
    svc = SchedulerService(seed_session)
    job = svc.register_job(job_name="monitoring:notify", job_type=JobType.NOTIFICATION_DISPATCH,
                           interval_seconds=900, now=NOW)
    assert job is not None
    # duplicate registration is idempotent
    assert svc.register_job(job_name="monitoring:notify", job_type=JobType.NOTIFICATION_DISPATCH,
                            interval_seconds=900, now=NOW) is None
    assert job in svc.due_jobs(NOW)


def test_scheduler_run_success_sets_next_run(seed_session):
    svc = SchedulerService(seed_session)
    job = svc.register_job(job_name="monitoring:notify", job_type=JobType.NOTIFICATION_DISPATCH,
                           interval_seconds=900, now=NOW)
    run = svc.run_job(job, now=NOW)
    assert run.status is SchedulerRunStatus.SUCCESS
    assert job.current_status is ScheduledJobStatus.SUCCESS
    assert job.next_run_at == NOW + timedelta(seconds=900)
    assert job.last_success_at == NOW


def test_scheduler_idempotent_same_bucket(seed_session):
    svc = SchedulerService(seed_session)
    job = svc.register_job(job_name="monitoring:notify", job_type=JobType.NOTIFICATION_DISPATCH,
                           interval_seconds=900, now=NOW)
    svc.run_job(job, now=NOW)
    run2 = svc.run_job(job, now=NOW)      # same interval bucket
    assert run2.status is SchedulerRunStatus.SKIPPED    # §21


def test_scheduler_retry_on_transient_then_permanent(seed_session, monkeypatch):
    svc = SchedulerService(seed_session)
    job = svc.register_job(job_name="flaky", job_type=JobType.NOTIFICATION_DISPATCH,
                           interval_seconds=900, now=NOW)
    job.max_retries = 2
    seed_session.flush()

    import scheduler.service as svc_mod

    def boom_transient(session, j, now):
        raise TransientJobError("temporary")
    monkeypatch.setattr(svc_mod, "get_handler", lambda jt: boom_transient)
    run = svc.run_job(job, now=NOW)
    assert run.status is SchedulerRunStatus.FAILED
    assert job.consecutive_failures == 1
    # transient failure backs off (earlier than a full interval)
    assert job.next_run_at == NOW + timedelta(seconds=job.retry_backoff_seconds)

    def boom_permanent(session, j, now):
        raise PermanentJobError("bad creds")
    monkeypatch.setattr(svc_mod, "get_handler", lambda jt: boom_permanent)
    later = NOW + timedelta(seconds=1000)
    run2 = svc.run_job(job, now=later, trigger="MANUAL")
    assert run2.status is SchedulerRunStatus.FAILED
    # permanent failure waits for the normal interval, not a fast retry
    assert job.next_run_at == later + timedelta(seconds=job.interval_seconds)


def test_scheduler_pause_resume(seed_session):
    svc = SchedulerService(seed_session)
    job = svc.register_job(job_name="monitoring:notify", job_type=JobType.NOTIFICATION_DISPATCH,
                           interval_seconds=900, now=NOW)
    svc.pause(job.id)
    assert job.current_status is ScheduledJobStatus.PAUSED
    assert job not in svc.due_jobs(NOW)
    svc.resume(job.id, now=NOW)
    assert job.current_status is ScheduledJobStatus.SCHEDULED
    assert job in svc.due_jobs(NOW)


def test_scheduler_run_records_audit_counters(seed_session):
    _seed_surge(seed_session)
    svc = SchedulerService(seed_session)
    job = svc.register_job(job_name="monitoring:notify", job_type=JobType.NOTIFICATION_DISPATCH,
                           interval_seconds=900, now=NOW)
    run = svc.run_job(job, now=NOW)
    assert run.status is SchedulerRunStatus.SUCCESS
    assert run.duration_seconds is not None
    assert run.alerts_generated >= 1        # real counters recorded (§41)


# --------------------------------------------------------------------------- #
# Reprocess + AI trigger gate (§34, §36)
# --------------------------------------------------------------------------- #
def test_should_trigger_ai_only_on_meaningful_change():
    from database.models import ChangeSignificance, LeadChangeEvent
    from scheduler.reprocess import should_trigger_ai
    minor = LeadChangeEvent(lead_id=1, change_type="SCORE_INCREASED",
                            significance=ChangeSignificance.LOW, dedup_key="a")
    major = LeadChangeEvent(lead_id=1, change_type="PRIORITY_CHANGED",
                            significance=ChangeSignificance.HIGH, dedup_key="b")
    assert should_trigger_ai([minor]) is False
    assert should_trigger_ai([major]) is True


# --------------------------------------------------------------------------- #
# APIs
# --------------------------------------------------------------------------- #
def test_api_scheduler_jobs_seeded(client):
    from config import get_settings
    body = client.get("/scheduler/jobs").json()
    assert body["total"] >= 7                       # maintenance jobs at minimum
    # scheduler_enabled reflects the deployment config (may be on when continuous
    # collection is enabled) — assert it mirrors the real setting, not a hard-coded default.
    assert body["scheduler_enabled"] == get_settings().scheduler_active


def test_api_alerts_empty(client):
    body = client.get("/alerts").json()
    assert body["total"] == 0 and body["unread_count"] == 0


def test_api_monitoring_dashboard(client):
    body = client.get("/monitoring/dashboard").json()
    assert body["data_mode"] == "REAL_ONLY"
    assert "pipeline" in body and "jobs" in body


def test_api_notification_preferences_roundtrip(client):
    body = client.get("/notification-preferences").json()
    assert "enabled_alert_types" in body
    upd = client.put("/notification-preferences", json={"hot_leads_only": True}).json()
    assert upd["hot_leads_only"] is True


def test_api_manual_run_and_status(client):
    jobs = client.get("/scheduler/jobs").json()["items"]
    notify = next(j for j in jobs if j["job_type"] == "NOTIFICATION_DISPATCH")
    run = client.post(f"/scheduler/jobs/{notify['id']}/run")
    assert run.status_code == 200 and run.json()["status"] in {"SUCCESS", "SKIPPED", "PARTIAL"}
    assert client.get("/scheduler/jobs/999999").status_code == 404


def test_api_admin_guard_enforced_when_key_set(client, monkeypatch):
    from config import settings as settings_mod
    settings = settings_mod.get_settings()
    monkeypatch.setattr(settings, "admin_api_key", "secret-key")
    jobs = client.get("/scheduler/jobs").json()["items"]
    jid = jobs[0]["id"]
    # No header → forbidden.
    assert client.post(f"/scheduler/jobs/{jid}/pause").status_code == 403
    # Correct header → allowed.
    ok = client.post(f"/scheduler/jobs/{jid}/pause", headers={"X-Admin-Key": "secret-key"})
    assert ok.status_code == 200
