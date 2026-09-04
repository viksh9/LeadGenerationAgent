"""FastAPI dependencies: database session lifecycle and settings."""

from __future__ import annotations

from collections.abc import Generator

from sqlalchemy.orm import Session, sessionmaker

from config import Settings, get_settings
from database.repository import create_session_factory

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
