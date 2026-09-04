"""Shared fixtures: an isolated per-test SQLite database and a synthetic lead."""

from __future__ import annotations

# Redirect the default DATABASE_URL to a throwaway file *before* settings are
# read, so tests that build the app (and its startup init_db) never touch the
# real development database. Per-test fixtures below use their own tmp DBs.
import os
import tempfile

_TEST_DB_DIR = tempfile.mkdtemp(prefix="lga-tests-")
os.environ.setdefault("DATABASE_URL", f"sqlite:///{_TEST_DB_DIR}/app.db")

from collections.abc import Iterator  # noqa: E402
from typing import Any  # noqa: E402

import pytest  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from database.models import LeadPriority, LeadStatus, SignalType  # noqa: E402
from database.repository import create_session_factory, get_engine, init_db  # noqa: E402


@pytest.fixture
def db_session(tmp_path) -> Iterator[Session]:
    """A Session bound to a throwaway SQLite file (never the dev database)."""
    engine = get_engine(f"sqlite:///{tmp_path / 'test.db'}")
    init_db(engine)
    factory = create_session_factory(engine)
    session = factory()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


@pytest.fixture
def sample_lead_data() -> dict[str, Any]:
    """Synthetic lead fixture — NorthStar Banking Technologies (BFSI)."""
    return {
        "company_name": "NorthStar Banking Technologies",
        "industry": "BFSI",
        "location": "Mumbai, IN",
        "company_size": "1001-5000",
        "company_website": "https://northstar-banking.example",
        "signal_type": SignalType.DIGITAL_TRANSFORMATION,
        "signal_title": "New digital banking transformation project + technology hiring",
        "signal_description": "Launching a cloud-native digital banking platform and "
        "hiring a delivery team across Java, AWS, and DevOps.",
        "source_name": "press_release",
        "source_url": "https://news.example/northstar-digital-banking",
        "technologies": ["Java", "Spring Boot", "AWS", "DevOps"],
        "project_name": "Digital Banking Platform",
        "project_value": 2500000.0,
        "estimated_hiring": 40,
        "hiring_roles": ["Java Developer", "DevOps Engineer", "Cloud Architect"],
        "poc_name": "Anita Desai",
        "poc_title": "VP of Engineering",
        "signal_confidence": 90.0,
        "lead_score": 82.0,
        "lead_priority": LeadPriority.HOT,
        "opportunity_summary": "Greenfield digital banking build with active tech hiring.",
        "recommended_action": "Book a platform architecture discovery call.",
        "status": LeadStatus.NEW,
    }
