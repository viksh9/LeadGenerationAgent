"""Unit tests for Indian location normalization."""

from __future__ import annotations

import pytest

from database.models import RemoteType
from ingestion.location import normalize_location


@pytest.mark.parametrize("text,city,state", [
    ("Bangalore", "Bengaluru", "Karnataka"),
    ("Bengaluru, Karnataka", "Bengaluru", "Karnataka"),
    ("HITEC City, Hyderabad", "Hyderabad", "Telangana"),
    ("Gurgaon", "Gurugram", "Haryana"),
    ("Bombay", "Mumbai", "Maharashtra"),
    ("New Delhi", "Delhi", "Delhi"),
    ("Cochin", "Kochi", "Kerala"),
    ("Pune, India", "Pune", "Maharashtra"),
])
def test_city_aliases(text, city, state):
    loc = normalize_location(text)
    assert loc.city == city
    assert loc.state == state
    assert loc.country == "India"


def test_remote_india():
    loc = normalize_location("Remote - India")
    assert loc.remote_type is RemoteType.REMOTE
    assert loc.country == "India"


def test_hybrid_beats_remote():
    assert normalize_location("Hybrid - Bengaluru").remote_type is RemoteType.HYBRID


def test_onsite():
    assert normalize_location("On-site, Pune").remote_type is RemoteType.ONSITE


def test_ambiguous_not_guessed():
    loc = normalize_location("Springfield")
    assert loc.city is None
    assert loc.country is None
    assert loc.remote_type is RemoteType.UNKNOWN


def test_empty():
    loc = normalize_location(None)
    assert loc.city is None and loc.country is None


def test_new_delhi_beats_delhi_substring():
    # Longest-alias-first ordering keeps "new delhi" -> Delhi (not a partial).
    assert normalize_location("New Delhi").city == "Delhi"
