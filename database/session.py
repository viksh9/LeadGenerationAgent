"""Engine creation, schema init, and session lifecycle for SQLite/SQLAlchemy."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker

from config import get_settings
from database.models import Base


def get_engine(url: str | None = None) -> Engine:
    database_url = url or get_settings().database_url
    connect_args = {"check_same_thread": False} if database_url.startswith("sqlite") else {}
    return create_engine(database_url, connect_args=connect_args, future=True)


def create_session_factory(engine: Engine | None = None) -> sessionmaker[Session]:
    engine = engine or get_engine()
    return sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False, class_=Session)


def init_db(engine: Engine | None = None) -> None:
    """Create tables if they do not already exist."""
    engine = engine or get_engine()
    Base.metadata.create_all(engine)


@contextmanager
def session_scope(session_factory: sessionmaker[Session] | None = None) -> Iterator[Session]:
    """Commit on success, rollback on error, always close the session."""
    factory = session_factory or create_session_factory()
    session = factory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
