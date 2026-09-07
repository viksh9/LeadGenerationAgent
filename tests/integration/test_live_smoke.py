"""OPT-IN production-like smoke workflow (§56). SKIPPED by default.

Runs only when RUN_LIVE_SMOKE_TESTS=true. Verifies real infrastructure health
against the CONFIGURED database + providers — it NEVER creates fake leads or
inserts synthetic business data to test the dashboard. It only reads real state
and checks connectivity/config truthfully.
"""

from __future__ import annotations

import os

import pytest

_LIVE = os.environ.get("RUN_LIVE_SMOKE_TESTS", "").lower() in {"1", "true", "yes"}

pytestmark = pytest.mark.skipif(
    not _LIVE, reason="live smoke tests are opt-in (set RUN_LIVE_SMOKE_TESTS=true)"
)


def test_live_smoke_real_infrastructure():
    from config.dotenv import load_dotenv
    load_dotenv()

    from config import get_settings
    from database.session import create_session_factory, get_engine, init_db
    from database.integrity import audit_database
    from crm.analytics import compute_crm_analytics

    settings = get_settings()
    engine = get_engine(settings.database_url)
    init_db(engine)                       # real DB reachable + schema present
    session = create_session_factory(engine)()
    try:
        # Real DB read: audit must run and report actual counts (no fabrication).
        audit = audit_database(session)
        assert audit.total_records >= 0
        # No synthetic business data may exist in the real database.
        assert audit.synthetic_total == 0, "synthetic records present in the real database"

        # Analytics compute over real data without inventing values.
        analytics = compute_crm_analytics(session)
        assert analytics.total_leads == sum(analytics.lead_status_counts.values())

        # Truthful provider status (report only; never asserts CONNECTED falsely).
        assert settings.email_config_status in {"NOT_CONFIGURED", "CONFIGURED"}
        assert settings.crm_config_status in {"NOT_CONFIGURED", "CONFIGURED"}
        assert settings.ai_config_status in {"NOT_CONFIGURED", "CONFIGURED", "DISABLED"}
    finally:
        session.close()
