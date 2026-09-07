"""Evidence freshness — is the evidence current for its signal type?

Configurable per signal type (config.evidence). Uses published/observed/updated
dates, closing/expiry dates, and explicit source status. Never invents dates:
missing dates yield low freshness + a warning, not a guess.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

from config.evidence import freshness_policy_for


@dataclass
class FreshnessResult:
    score: int
    is_stale: bool
    age_days: Optional[int]
    reason: str


_EXPIRED_STATUSES = {"expired", "closed", "filled", "cancelled", "inactive"}
_ACTIVE_STATUSES = {"active", "open", "live"}


def _naive(dt: Optional[datetime]) -> Optional[datetime]:
    if dt is None:
        return None
    return dt.astimezone(timezone.utc).replace(tzinfo=None) if dt.tzinfo else dt


def compute_freshness(
    *,
    signal_type: Optional[str],
    published_at: Optional[datetime] = None,
    observed_at: Optional[datetime] = None,
    updated_at: Optional[datetime] = None,
    closing_date: Optional[datetime] = None,
    source_status: Optional[str] = None,
    now: Optional[datetime] = None,
) -> FreshnessResult:
    now = _naive(now) or datetime.now(timezone.utc).replace(tzinfo=None)
    policy = freshness_policy_for(signal_type)
    status = (source_status or "").lower()

    # Explicit expiry / closed status dominates (e.g. expired tender).
    if closing_date is not None and _naive(closing_date) < now:
        return FreshnessResult(15, True, None, "Closing/expiry date has passed — stale.")
    if status in _EXPIRED_STATUSES:
        return FreshnessResult(12, True, None, f"Source marks the item {status} — stale.")

    ref = _naive(updated_at) or _naive(published_at) or _naive(observed_at)
    if ref is None:
        return FreshnessResult(30, False, None, "No reliable date available — freshness uncertain.")

    age = max(0, (now - ref).days)
    if age <= policy.very_recent_days:
        score, reason = 95, f"Very recent ({age}d)."
    elif age <= policy.recent_days:
        score, reason = 78, f"Recent ({age}d)."
    elif age <= policy.stale_after_days:
        # Linear decay from 70 down to ~35 across the window.
        span = max(1, policy.stale_after_days - policy.recent_days)
        score = int(70 - 35 * (age - policy.recent_days) / span)
        reason = f"Ageing ({age}d)."
    else:
        # Beyond the window: stale, unless the source explicitly says still active.
        if status in _ACTIVE_STATUSES:
            return FreshnessResult(policy.active_floor, False, age,
                                   f"Old ({age}d) but source indicates still active.")
        return FreshnessResult(20, True, age, f"Older than {policy.stale_after_days}d — stale.")

    if status in _ACTIVE_STATUSES:
        score = max(score, policy.active_floor)
        reason += " Source indicates active."
    return FreshnessResult(score, False, age, reason)
