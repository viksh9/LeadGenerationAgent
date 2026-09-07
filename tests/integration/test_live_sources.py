"""OPT-IN live source connection tests (real external network).

These are SKIPPED by default. They run ONLY when RUN_LIVE_SOURCE_TESTS=true and
the relevant credentials are present in the environment — then they make a real
request to verify authentication, HTTP success, and basic response structure.

They never assert on a specific company/job (external data changes); they assert
structure and successful field mapping only, and they never fabricate credentials
or a successful response.

    RUN_LIVE_SOURCE_TESTS=true ADZUNA_APP_ID=... ADZUNA_APP_KEY=... \
        pytest tests/integration/test_live_sources.py -q
"""

from __future__ import annotations

import os

import pytest

_LIVE = os.environ.get("RUN_LIVE_SOURCE_TESTS", "").lower() in {"1", "true", "yes"}

pytestmark = pytest.mark.skipif(
    not _LIVE, reason="live source tests are opt-in (set RUN_LIVE_SOURCE_TESTS=true)"
)


def _require(*env_vars: str) -> None:
    missing = [v for v in env_vars if not os.environ.get(v)]
    if missing:
        pytest.skip(f"missing credentials: {', '.join(missing)}")


def test_adzuna_connection():
    _require("ADZUNA_APP_ID", "ADZUNA_APP_KEY")
    from collectors.base import FetchRequest, HealthStatus
    from collectors.jobs.adzuna import AdzunaJobCollector
    from collectors.jobs.config import load_adzuna_config
    from collectors.source_registry import get_registry

    collector = AdzunaJobCollector(get_registry().get("adzuna"), config=load_adzuna_config())
    assert collector.health_check().status is HealthStatus.HEALTHY

    result = collector.fetch(FetchRequest(query="python developer", page=1, limit=5))
    assert result.source_id == "adzuna"
    assert isinstance(result.records, list)
    for draft in result.records:                    # structural assertions only
        assert draft.source_id == "adzuna"
        assert draft.is_synthetic is False
        assert draft.source_url                      # real source URL present
        assert draft.external_id                     # real provider id present


def test_jooble_connection():
    _require("JOOBLE_API_KEY")
    from collectors.base import FetchRequest, HealthStatus
    from collectors.jobs.jooble import JoobleJobCollector, load_jooble_config
    from collectors.source_registry import get_registry

    collector = JoobleJobCollector(get_registry().get("jooble"), config=load_jooble_config())
    assert collector.health_check().status is HealthStatus.HEALTHY

    result = collector.fetch(FetchRequest(query="python developer", location="India", page=1))
    assert result.source_id == "jooble"
    assert isinstance(result.records, list)
    for draft in result.records:
        assert draft.source_id == "jooble"
        assert draft.is_synthetic is False
        assert draft.source_url
        assert draft.external_id
