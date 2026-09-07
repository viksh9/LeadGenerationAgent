"""Persistent per-source request-budget tracking.

Some sources have a hard LIFETIME request quota (notably Jooble's free REST plan:
500 requests per key, absolute — not per-period). This module persists a request
counter in the source_health table so the application cannot accidentally burn the
quota across runs. Generic infrastructure — the budget value comes from each
source's configuration, never hard-coded here.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from database.models import SourceHealth

# Warn when this fraction of the budget has been consumed.
WARN_THRESHOLD = 0.8


@dataclass
class BudgetState:
    source_id: str
    budget: Optional[int]        # None => no fixed lifetime budget
    used: int
    @property
    def remaining(self) -> Optional[int]:
        return None if self.budget is None else max(0, self.budget - self.used)

    @property
    def exhausted(self) -> bool:
        return self.budget is not None and self.used >= self.budget

    @property
    def near_limit(self) -> bool:
        return self.budget is not None and self.used >= int(self.budget * WARN_THRESHOLD)


def _row(session: Session, source_id: str) -> SourceHealth:
    row = session.scalar(select(SourceHealth).where(SourceHealth.source_id == source_id))
    if row is None:
        row = SourceHealth(source_id=source_id)
        session.add(row)
        session.flush()
    return row


def get_state(session: Session, source_id: str, *, budget: Optional[int] = None) -> BudgetState:
    """Current budget state. If ``budget`` is given it is recorded on the row."""
    row = _row(session, source_id)
    if budget is not None and row.request_budget != budget:
        row.request_budget = budget
        session.commit()
    effective = row.request_budget if budget is None else budget
    return BudgetState(source_id=source_id, budget=effective, used=row.requests_used or 0)


def record_usage(session: Session, source_id: str, requests: int, *, budget: Optional[int] = None) -> BudgetState:
    """Add ``requests`` to the persistent counter and return the new state."""
    row = _row(session, source_id)
    if budget is not None:
        row.request_budget = budget
    row.requests_used = (row.requests_used or 0) + max(0, requests)
    session.commit()
    return BudgetState(source_id=source_id, budget=row.request_budget, used=row.requests_used)
