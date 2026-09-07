"""Pure-logic unit tests for the monitoring layer (§45): change classification,
trend/surge math, lead/opportunity diffs, source-health transitions, alert
severity/dedup. No DB, no network, deterministic.
"""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from database.models import (
    AlertSeverity,
    AlertType,
    ChangeSignificance,
    ChangeType,
    LeadPriority,
    SourceConnectionStatus,
    SourceHealthEventType,
    TrendStatus,
)
from monitoring.change_detection import JobSnapshot, classify_job_change
from monitoring.config import DEFAULT_HIRING_SURGE, DEFAULT_TREND
from monitoring.lead_changes import LeadState, diff_lead
from monitoring.opportunity_changes import OpportunityState, diff_opportunity
from monitoring.source_health import evaluate_transition
from monitoring.trends import classify_trend, evaluate_surge

NOW = datetime(2026, 9, 7, 12, 0, 0)


def _snap(**over):
    base = dict(canonical_job_id=1, content_hash="h1", job_status="ACTIVE",
                title="Java Developer", technologies=("java",))
    base.update(over)
    return JobSnapshot(**base)


# --------------------------------------------------------------------------- #
# Change classification (§6, §7)
# --------------------------------------------------------------------------- #
def test_change_new():
    assert classify_job_change(None, _snap(), now=NOW).change_type is ChangeType.NEW


def test_change_removed_not_closed():
    v = classify_job_change(_snap(), None, now=NOW)
    assert v.change_type is ChangeType.REMOVED_FROM_SOURCE     # NOT closed (§6)


def test_change_unchanged():
    a = _snap()
    assert classify_job_change(a, a, now=NOW).change_type is ChangeType.UNCHANGED


def test_change_updated_with_field_diffs():
    a = _snap(content_hash="h1", technologies=("java",))
    b = _snap(content_hash="h2", technologies=("java", "aws"))
    v = classify_job_change(a, b, now=NOW)
    assert v.change_type is ChangeType.UPDATED
    assert any(fc.field_name == "technologies" for fc in v.field_changes)
    assert v.significance is ChangeSignificance.MEDIUM


def test_change_closed_is_critical():
    a = _snap(job_status="ACTIVE")
    b = _snap(job_status="EXPIRED")
    v = classify_job_change(a, b, now=NOW)
    assert v.change_type is ChangeType.CLOSED and v.significance is ChangeSignificance.CRITICAL


def test_change_reopened():
    closed = _snap(job_status="EXPIRED")
    active = _snap(job_status="ACTIVE")
    assert classify_job_change(closed, active, now=NOW).change_type is ChangeType.REOPENED


def test_change_stale_when_flagged():
    a = _snap()
    assert classify_job_change(a, a, now=NOW, is_stale=True).change_type is ChangeType.STALE


def test_change_contradicted():
    a = _snap(content_hash="h1")
    b = _snap(content_hash="h2")
    assert classify_job_change(a, b, now=NOW, is_contradicted=True).change_type is ChangeType.CONTRADICTED


def test_change_requires_a_snapshot():
    with pytest.raises(ValueError):
        classify_job_change(None, None, now=NOW)


# --------------------------------------------------------------------------- #
# Trend + surge (§12, §13, §14)
# --------------------------------------------------------------------------- #
def test_trend_insufficient_data():
    assert classify_trend(1, 0, config=DEFAULT_TREND).status is TrendStatus.INSUFFICIENT_DATA


def test_trend_rapidly_increasing():
    assert classify_trend(18, 5).status is TrendStatus.RAPIDLY_INCREASING


def test_trend_stable():
    assert classify_trend(6, 5).status is TrendStatus.STABLE


def test_trend_rapidly_decreasing():
    assert classify_trend(3, 10).status is TrendStatus.RAPIDLY_DECREASING


def test_surge_detected_5_to_18():
    res = evaluate_surge(18, 5, label="HIRING_SURGE", config=DEFAULT_HIRING_SURGE)
    assert res.is_surge is True


def test_surge_ignores_small_numbers():
    # 1 -> 3 must NOT be a surge (§13 — do not treat tiny bumps as staffing need).
    assert evaluate_surge(3, 1, label="HIRING_SURGE", config=DEFAULT_HIRING_SURGE).is_surge is False


def test_technology_surge_2_to_12():
    assert evaluate_surge(12, 2, label="AWS_DEMAND_SURGE").is_surge is True


# --------------------------------------------------------------------------- #
# Lead change diff (§10)
# --------------------------------------------------------------------------- #
def _lead(**over):
    base = dict(lead_id=1, company_id=1, company_name="Acme", lead_score=50.0,
                lead_priority=LeadPriority.WARM.value, evidence_confidence=60,
                verification_status="VERIFIED", lead_readiness="REVIEW_REQUIRED",
                conflict_count=0, verified_contact_count=0)
    base.update(over)
    return LeadState(**base)


def test_lead_score_increase_emits_event_and_finding():
    events, findings = diff_lead(_lead(lead_score=50), _lead(lead_score=70), now=NOW)
    assert any(e.change_type == "SCORE_INCREASED" for e in events)
    assert any(f.alert_type is AlertType.LEAD_SCORE_INCREASED for f in findings)


def test_lead_score_jitter_below_threshold_ignored():
    events, _ = diff_lead(_lead(lead_score=50), _lead(lead_score=52), now=NOW)
    assert not any(e.change_type.startswith("SCORE") for e in events)


def test_lead_priority_upgrade_to_hot():
    events, findings = diff_lead(
        _lead(lead_priority=LeadPriority.WARM.value),
        _lead(lead_priority=LeadPriority.HOT.value), now=NOW,
    )
    assert any(e.change_type == "PRIORITY_CHANGED" for e in events)
    assert any(f.alert_type is AlertType.NEW_HIGH_INTENT_LEAD for f in findings)


def test_lead_new_hot_lead_finding():
    _, findings = diff_lead(None, _lead(lead_priority=LeadPriority.HOT.value), now=NOW)
    assert any(f.alert_type is AlertType.NEW_HIGH_INTENT_LEAD for f in findings)


def test_lead_conflict_detected():
    events, findings = diff_lead(_lead(conflict_count=0), _lead(conflict_count=1), now=NOW)
    assert any(e.change_type == "CONFLICT_DETECTED" for e in events)
    assert any(f.alert_type is AlertType.EVIDENCE_CONFLICT for f in findings)


def test_lead_became_stale():
    events, findings = diff_lead(
        _lead(verification_status="VERIFIED"), _lead(verification_status="STALE"), now=NOW,
    )
    assert any(e.change_type == "EVIDENCE_STALE" for e in events)
    assert any(f.alert_type is AlertType.EVIDENCE_STALE for f in findings)


# --------------------------------------------------------------------------- #
# Opportunity diff (§11)
# --------------------------------------------------------------------------- #
def test_opportunity_created():
    events, _ = diff_opportunity(None, OpportunityState(opportunity_id=1, confidence=60), now=NOW)
    assert any(e.change_type == "OPPORTUNITY_CREATED" for e in events)


def test_opportunity_recompute_no_material_change_no_event():
    before = OpportunityState(opportunity_id=1, confidence=60, evidence_confidence=50)
    after = OpportunityState(opportunity_id=1, confidence=63, evidence_confidence=50)
    events, _ = diff_opportunity(before, after, now=NOW)
    assert events == []      # recalculation alone is not a change (§11)


def test_opportunity_strengthened():
    before = OpportunityState(opportunity_id=1, confidence=50)
    after = OpportunityState(opportunity_id=1, confidence=75)
    events, _ = diff_opportunity(before, after, now=NOW)
    assert any(e.change_type == "OPPORTUNITY_STRENGTHENED" for e in events)


# --------------------------------------------------------------------------- #
# Source-health transitions (§19, §20)
# --------------------------------------------------------------------------- #
def test_source_failure_event_and_finding():
    event, finding = evaluate_transition(
        "adzuna", SourceConnectionStatus.CONNECTED.value, SourceConnectionStatus.ERROR.value,
        last_failure_at=NOW, last_success_at=None, now=NOW, message="boom",
    )
    assert event is not None and event.event_type is SourceHealthEventType.SOURCE_FAILED
    assert finding is not None and finding.alert_type is AlertType.SOURCE_FAILURE


def test_source_recovery_event():
    event, finding = evaluate_transition(
        "adzuna", SourceConnectionStatus.ERROR.value, SourceConnectionStatus.CONNECTED.value,
        last_failure_at=None, last_success_at=NOW, now=NOW,
    )
    assert event.event_type is SourceHealthEventType.SOURCE_RECOVERED
    assert finding.alert_type is AlertType.SOURCE_RECOVERED


def test_source_no_transition_no_event():
    # Same status → no duplicate event (§20).
    event, finding = evaluate_transition(
        "adzuna", SourceConnectionStatus.CONNECTED.value, SourceConnectionStatus.CONNECTED.value,
        last_failure_at=None, last_success_at=NOW, now=NOW,
    )
    assert event is None and finding is None


def test_source_auth_failure_is_high_severity():
    _, finding = evaluate_transition(
        "adzuna", SourceConnectionStatus.CONNECTED.value,
        SourceConnectionStatus.AUTHENTICATION_FAILED.value,
        last_failure_at=NOW, last_success_at=None, now=NOW,
    )
    assert finding.severity is AlertSeverity.HIGH
