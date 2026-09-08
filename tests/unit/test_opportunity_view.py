"""Opportunity view derivation (Prompt 49) — backend mirror of the Opportunity tab.

Locks the band boundaries and type mapping so the export stays byte-identical to
frontend/src/services/opportunities.ts. Pure/offline. Nothing is fabricated:
UNKNOWN/Not Available are surfaced honestly when inputs are absent.
"""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from database.models import Lead, SignalType
from intelligence.opportunity_view import (
    derive_opportunity_type,
    derive_staffing_need,
    derive_urgency,
    derive_opportunity_view,
    opportunity_cell,
)

NOW = datetime(2026, 9, 5, 12, 0, 0)


def _lead(**kw) -> Lead:
    return Lead(company_name="X", normalized_company_name="x", **kw)


# --- staffing bands: >=25 HIGH, >=10 MEDIUM, >0 LOW, else UNKNOWN ----------- #
@pytest.mark.parametrize("hiring,expected", [
    (None, "UNKNOWN"), (0, "UNKNOWN"), (1, "LOW"), (9, "LOW"),
    (10, "MEDIUM"), (24, "MEDIUM"), (25, "HIGH"), (500, "HIGH"),
])
def test_staffing_bands(hiring, expected):
    assert derive_staffing_need(hiring) == expected


# --- urgency bands: <=7 CRITICAL, <=30 HIGH, <=60 MEDIUM, else LOW ---------- #
@pytest.mark.parametrize("days,expected", [
    (0, "CRITICAL"), (7, "CRITICAL"), (8, "HIGH"), (30, "HIGH"),
    (31, "MEDIUM"), (60, "MEDIUM"), (61, "LOW"), (400, "LOW"),
])
def test_urgency_bands(days, expected):
    assert derive_urgency(NOW - timedelta(days=days), NOW) == expected


def test_urgency_unknown_without_signal_date():
    assert derive_urgency(None, NOW) == "UNKNOWN"


# --- opportunity type mapping (matches deriveOpportunityType) --------------- #
@pytest.mark.parametrize("signal,hiring,expected", [
    (SignalType.HIRING, 0, "NORMAL_HIRING"),
    (SignalType.HIRING, 10, "STAFF_AUGMENTATION"),
    (SignalType.HIRING, 25, "LARGE_SCALE_RAMP_UP"),   # large figure escalates
    (SignalType.EXPANSION, 5, "LARGE_SCALE_RAMP_UP"),
    (None, 100, "LOW_CONFIDENCE"),                    # no signal -> low confidence, never invented
])
def test_type_mapping(signal, hiring, expected):
    assert derive_opportunity_type(_lead(signal_type=signal, estimated_hiring=hiring)) == expected


def test_view_carries_actual_estimated_hiring():
    lead = _lead(signal_type=SignalType.HIRING, estimated_hiring=30,
                 signal_date=NOW - timedelta(days=2), technologies=["Java"])
    view = derive_opportunity_view(lead, signal_date=lead.signal_date, now=NOW)
    assert view.estimated_team == 30 and view.staffing_need == "HIGH"


def test_cell_is_type_label_only():
    # The Opportunity cell is just the type label — no staffing/team/urgency lines.
    lead = _lead(signal_type=SignalType.HIRING, estimated_hiring=30,
                 signal_date=NOW - timedelta(days=2))
    cell = opportunity_cell(derive_opportunity_view(lead, signal_date=lead.signal_date, now=NOW))
    assert cell == "Large-Scale Ramp-Up"
    assert "\n" not in cell and "Staffing" not in cell


def test_cell_none_estimate_still_type_only():
    view = derive_opportunity_view(_lead(), now=NOW)
    assert view.estimated_team is None
    assert opportunity_cell(view) == "Low Confidence"
