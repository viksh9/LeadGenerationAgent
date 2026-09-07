"""Tests for the controlled Adzuna query strategy (bounded, mode-driven)."""

from __future__ import annotations

import pytest

from collectors.jobs.query_strategy import VALID_MODES, build_plan, describe_plan

TERMS = ["Java developer", "Python developer", "AWS engineer", "DevOps engineer", "SDET"]
LOCS = ["Bengaluru", "Hyderabad", "Pune", "Chennai", "Mumbai"]


def test_role_first_is_india_wide_no_city_fanout():
    plan = build_plan(mode="ROLE_FIRST", search_terms=TERMS, locations=LOCS,
                      max_pages=1, max_requests=30)
    assert len(plan) == len(TERMS)                      # one per role, not roles×cities
    assert {r.location for r in plan} == {None}          # India-wide (country path scopes it)
    assert {r.query for r in plan} == set(TERMS)


def test_technology_first_same_shape():
    plan = build_plan(mode="TECHNOLOGY_FIRST", search_terms=TERMS, locations=LOCS,
                      max_pages=1, max_requests=30)
    assert {r.location for r in plan} == {None}
    assert len(plan) == len(TERMS)


def test_location_first_one_query_per_city():
    plan = build_plan(mode="LOCATION_FIRST", search_terms=TERMS, locations=LOCS,
                      max_pages=1, max_requests=30)
    assert {r.location for r in plan} == set(LOCS)
    assert len({r.query for r in plan}) == 1             # single broad query per city


def test_pagination_applied_per_query():
    plan = build_plan(mode="ROLE_FIRST", search_terms=TERMS[:2], locations=LOCS,
                      max_pages=3, max_requests=30)
    assert len(plan) == 2 * 3
    assert max(r.page for r in plan) == 3


def test_hard_request_cap_enforced():
    plan = build_plan(mode="ROLE_FIRST", search_terms=TERMS * 50, locations=LOCS,
                      max_pages=3, max_requests=12)
    assert len(plan) == 12                               # never exceeds the cap


def test_plan_is_deduplicated():
    plan = build_plan(mode="ROLE_FIRST", search_terms=["Java", "Java", "Java"],
                      locations=LOCS, max_pages=1, max_requests=30)
    assert len(plan) == 1


def test_unknown_mode_raises():
    with pytest.raises(ValueError):
        build_plan(mode="EVERYTHING", search_terms=TERMS, locations=LOCS,
                   max_pages=1, max_requests=5)


def test_describe_plan_summary():
    plan = build_plan(mode="ROLE_FIRST", search_terms=TERMS, locations=LOCS,
                      max_pages=2, max_requests=30)
    d = describe_plan(plan)
    assert d["requests"] == len(plan)
    assert d["distinct_queries"] == len(TERMS)
    assert d["max_page"] == 2


def test_all_modes_respect_cap():
    for mode in VALID_MODES:
        plan = build_plan(mode=mode, search_terms=TERMS * 10, locations=LOCS * 10,
                          max_pages=5, max_requests=7)
        assert len(plan) <= 7
