"""Tests for the persistent per-source request budget (Jooble 500-lifetime cap)."""

from __future__ import annotations

from collectors.source_budget import BudgetState, get_state, record_usage


def test_budget_records_and_reports(seed_session):
    state = get_state(seed_session, "jooble", budget=500)
    assert state.budget == 500 and state.used == 0
    assert state.remaining == 500 and not state.exhausted

    state = record_usage(seed_session, "jooble", 3, budget=500)
    assert state.used == 3 and state.remaining == 497

    state = record_usage(seed_session, "jooble", 2, budget=500)
    assert state.used == 5


def test_budget_persists_across_calls(seed_session):
    record_usage(seed_session, "jooble", 10, budget=500)
    # Fresh state read reflects the persisted counter.
    assert get_state(seed_session, "jooble").used == 10


def test_budget_exhaustion_and_warning():
    near = BudgetState(source_id="jooble", budget=500, used=400)
    assert near.near_limit and not near.exhausted
    full = BudgetState(source_id="jooble", budget=500, used=500)
    assert full.exhausted and full.remaining == 0


def test_no_budget_means_unlimited(seed_session):
    state = get_state(seed_session, "adzuna")            # no budget set
    assert state.budget is None
    assert state.remaining is None and not state.exhausted
