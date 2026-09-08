"""Lightweight performance smoke test (§48, §66).

Seeds an ISOLATED throwaway database (never production) with a few hundred REAL-
shaped rows and asserts key read endpoints respond within a generous bound. This
is a regression guard against accidental O(n^2)/N+1 blowups, not a load test.
Thresholds are deliberately loose to stay stable across machines/CI.
"""

from __future__ import annotations

import time

import pytest

import api.main
from api.dependencies import get_session
from database.models import DataProvenance, Lead, LeadPriority, LeadStatus

_SEED = 300
_MAX_SECONDS = 3.0   # generous; a healthy paged query is well under this


def _seed_leads(session, n: int) -> None:
    for i in range(n):
        session.add(Lead(
            company_name=f"Company {i}", normalized_company_name=f"company {i}",
            lead_score=float(i % 100), lead_priority=LeadPriority.WARM,
            status=LeadStatus.NEW, data_provenance=DataProvenance.REAL,
        ))
    session.flush()


@pytest.mark.parametrize("path,params", [
    ("/leads", {"page_size": 50}),
    ("/crm/analytics", {}),
    ("/monitoring/metrics", {}),
    ("/monitoring/dashboard", {}),
])
def test_read_endpoints_are_reasonably_fast(client, path, params):
    session = next(api.main.app.dependency_overrides[get_session]())
    _seed_leads(session, _SEED)
    session.commit()
    session.close()

    start = time.monotonic()
    r = client.get(path, params=params)
    elapsed = time.monotonic() - start

    assert r.status_code == 200
    assert elapsed < _MAX_SECONDS, f"{path} took {elapsed:.2f}s for {_SEED} leads (bound {_MAX_SECONDS}s)"
