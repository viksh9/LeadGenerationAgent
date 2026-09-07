"""Role-based access control + in-process rate limiting (§42, §43).

RBAC is additive and does NOT break the existing open, single-user local app:
* If ``ADMIN_API_KEY`` is UNSET, every request resolves to ADMIN — the app stays
  fully open locally, exactly as before this change.
* If ``ADMIN_API_KEY`` IS set, a valid ``X-Admin-Key`` grants ADMIN; otherwise the
  role is taken from the ``X-Role`` header (SALES / RESEARCHER / VIEWER, default
  VIEWER). ADMIN is permitted for every guarded action.

Rate limiting reuses the in-process token/window limiter (per-process, not
distributed). Applied to expensive/abusable endpoints (email send, webhooks, AI).
"""

from __future__ import annotations

import hmac
import time

from fastapi import Header

from api.dependencies import ForbiddenError
from config import get_settings
from database.models import UserRole

_ROLE_RANK = {UserRole.VIEWER: 0, UserRole.RESEARCHER: 1, UserRole.SALES: 1, UserRole.ADMIN: 3}


def resolve_role(x_admin_key: str | None, x_role: str | None) -> UserRole:
    settings = get_settings()
    configured = settings.admin_api_key
    if not configured:
        return UserRole.ADMIN   # local single-user: fully open, unchanged behaviour
    if x_admin_key and hmac.compare_digest(str(x_admin_key), str(configured)):
        return UserRole.ADMIN
    if x_role:
        try:
            return UserRole(x_role.strip().upper())
        except ValueError:
            return UserRole.VIEWER
    return UserRole.VIEWER


def require_role(*allowed: UserRole):
    """Dependency factory. ADMIN always passes; otherwise the caller's role must be
    in ``allowed``. Read endpoints typically allow VIEWER; mutations require SALES
    or ADMIN; provider/scheduler config requires ADMIN."""
    allowed_set = set(allowed) | {UserRole.ADMIN}

    def _dep(
        x_admin_key: str | None = Header(default=None),
        x_role: str | None = Header(default=None),
    ) -> UserRole:
        role = resolve_role(x_admin_key, x_role)
        if role not in allowed_set:
            raise ForbiddenError(
                f"This action requires one of {sorted(r.value for r in allowed_set)}; "
                f"your role is {role.value}."
            )
        return role

    return _dep


# --------------------------------------------------------------------------- #
# Rate limiting (in-process rolling window per key).
# --------------------------------------------------------------------------- #
class _RateLimitError(ForbiddenError):
    def __init__(self, message: str = "Rate limit exceeded"):
        super().__init__(message)
        self.status_code = 429
        self.code = "rate_limited"


_WINDOWS: dict[str, list[float]] = {}


def _allow(key: str, per_minute: int, *, ts: float) -> bool:
    if per_minute <= 0:
        return True
    window = _WINDOWS.setdefault(key, [])
    cutoff = ts - 60
    while window and window[0] < cutoff:
        window.pop(0)
    if len(window) >= per_minute:
        return False
    window.append(ts)
    return True


def rate_limit(key: str, per_minute: int):
    """Dependency factory enforcing at most ``per_minute`` requests to ``key``."""

    def _dep() -> None:
        if not _allow(key, per_minute, ts=time.time()):
            raise _RateLimitError(f"Rate limit exceeded for {key} ({per_minute}/min).")

    return _dep


def reset_rate_limits() -> None:
    """Test helper to clear rate-limit state between tests."""
    _WINDOWS.clear()
