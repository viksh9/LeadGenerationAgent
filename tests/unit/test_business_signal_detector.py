"""Unit tests for business-signal detection, value/date extraction, relevance."""

from __future__ import annotations

from datetime import datetime

import pytest

from config.business_signals import BUSINESS_SOURCE_CONFIDENCE
from database.models import BusinessSignalType, SignalStrength
from intelligence.business_signal_detector import (
    BusinessSignalDetector,
    extract_project_value,
    signal_age_days,
)

D = BusinessSignalDetector()


@pytest.mark.parametrize("text,expected", [
    ("Acme Tech awarded the project to build a new digital platform", BusinessSignalType.PROJECT_AWARD),
    ("Acme Tech wins contract for IT services modernization", BusinessSignalType.CONTRACT),
    ("Government issues RFP for a cloud data platform", BusinessSignalType.TENDER),
    ("Acme Bank begins a digital transformation program with cloud", BusinessSignalType.DIGITAL_TRANSFORMATION),
    ("Retailer announces cloud migration to AWS", BusinessSignalType.CLOUD_MIGRATION),
    ("Acme launches an AI initiative using generative AI", BusinessSignalType.AI_INITIATIVE),
    ("Acme Tech opens new delivery center in Pune for software", BusinessSignalType.DELIVERY_CENTER_EXPANSION),
    ("Acme partners with a cloud provider on technology", BusinessSignalType.PARTNERSHIP),
    ("Acme seeks a staff augmentation partner for a new software platform", BusinessSignalType.VENDOR_REQUIREMENT),
    ("Acme acquires a cybersecurity firm", BusinessSignalType.ACQUISITION),
    ("Bank signs IT outsourcing deal with managed services provider", BusinessSignalType.OUTSOURCING),
])
def test_signal_type_detection(text, expected):
    assert D.detect(text).signal_type is expected


def test_technology_extraction():
    r = D.detect("Company migrates to AWS and Kubernetes with a Java and Python platform")
    assert "AWS" in r.technologies and "Java" in r.technologies


@pytest.mark.parametrize("text,value,currency", [
    ("project worth ₹500 crore", 5_000_000_000, "INR"),
    ("deal valued at $20 million", 20_000_000, "USD"),
    ("contract of INR 500 Cr", 5_000_000_000, "INR"),
    ("Rs 5,00,000 project", 500_000, "INR"),
])
def test_project_value_extraction(text, value, currency):
    v, cur, original = extract_project_value(text)
    assert v == value and cur == currency and original


def test_project_value_not_inferred_from_counts():
    assert extract_project_value("hiring 500 engineers for a large project") == (None, None, None)
    assert D.detect("Company announces a large project").project_value is None


def test_relevance_filters_non_it():
    assert D.detect("Local cricket team wins the tournament").is_relevant is False
    assert D.detect("Bank wins contract for IT services modernization").is_relevant is True


def test_weak_signal_handling():
    r = D.detect("Two companies announce a partnership")  # no IT evidence
    assert r.is_relevant is False
    assert r.signal_strength is SignalStrength.WEAK


def test_strong_signal_with_value():
    r = D.detect("Infosys awarded the project worth ₹500 crore for cloud migration")
    assert r.signal_strength is SignalStrength.STRONG


def test_empty_text():
    r = D.detect(None, None)
    assert r.signal_type is BusinessSignalType.OTHER and r.is_relevant is False


def test_signal_age_days():
    now = datetime(2026, 9, 5)
    assert signal_age_days(datetime(2026, 9, 3), now) == 2
    assert signal_age_days(datetime(2026, 3, 1), now) > 90
    assert signal_age_days(None, now) is None


def test_source_confidence_config():
    assert BUSINESS_SOURCE_CONFIDENCE["government_open_data"] > BUSINESS_SOURCE_CONFIDENCE["rss_news"]
