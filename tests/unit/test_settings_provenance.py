"""The synthetic-lead visibility default derives from environment safely."""

from __future__ import annotations

from config.settings import Settings


def test_production_hides_synthetic_by_default():
    assert Settings(environment="production").synthetic_leads_visible is False


def test_non_production_shows_synthetic_by_default():
    assert Settings(environment="development").synthetic_leads_visible is True
    assert Settings(environment="test").synthetic_leads_visible is True


def test_explicit_override_wins():
    assert Settings(environment="production", show_synthetic_leads=True).synthetic_leads_visible is True
    assert Settings(environment="development", show_synthetic_leads=False).synthetic_leads_visible is False
