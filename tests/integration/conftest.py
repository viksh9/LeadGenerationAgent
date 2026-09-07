"""Shared fixtures for API integration tests.

Provides a `client` bound to a throwaway SQLite database so the real development
database is never touched.
"""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import sessionmaker

import api.main
from api.dependencies import get_session
from database.repository import get_engine, init_db


@pytest.fixture
def client(tmp_path):
    engine = get_engine(f"sqlite:///{tmp_path / 'contract.db'}")
    init_db(engine)
    factory = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)

    def override():
        session = factory()
        try:
            yield session
        finally:
            session.close()

    api.main.app.dependency_overrides[get_session] = override
    yield TestClient(api.main.app)
    api.main.app.dependency_overrides.clear()
