"""FastAPI dependencies: database session lifecycle and settings."""

from __future__ import annotations

from collections.abc import Generator

from fastapi import Header
from sqlalchemy.orm import Session, sessionmaker

from config import Settings, get_settings
from config.exceptions import AppError
from database.repository import create_session_factory


class ForbiddenError(AppError):
    """Admin-only action attempted without a valid admin key."""

    def __init__(self, message: str = "Forbidden") -> None:
        super().__init__(message, status_code=403, code="forbidden")

# One session factory for the process; each request gets its own session.
SessionFactory: sessionmaker[Session] = create_session_factory()


def get_session() -> Generator[Session, None, None]:
    """Yield a request-scoped DB session and always close it."""
    session = SessionFactory()
    try:
        yield session
    finally:
        session.close()


def get_app_settings() -> Settings:
    return get_settings()


def require_admin(x_admin_key: str | None = Header(default=None)) -> None:
    """Guard for operational/admin actions (scheduler control, §39/§44).

    This is the app's first auth primitive. Policy:
    * If ``ADMIN_API_KEY`` is unset (local single-user default), actions are
      allowed — matching the existing unauthenticated app.
    * If it IS set, mutating scheduler endpoints require a matching
      ``X-Admin-Key`` header; otherwise the request is rejected 403.

    The key is compared with a constant-time check and never logged/echoed.
    """
    import hmac

    settings = get_settings()
    configured = settings.admin_api_key
    if not configured:
        return  # no admin key configured → allowed (local single-user)
    if not x_admin_key or not hmac.compare_digest(str(x_admin_key), str(configured)):
        raise ForbiddenError("A valid X-Admin-Key header is required for this action.")
