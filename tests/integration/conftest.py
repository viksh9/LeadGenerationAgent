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
from database.session import create_session_factory
from tests.fixtures import synthetic_leads


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


@pytest.fixture
def seed_session(tmp_path):
    """A Session bound to a throwaway SQLite DB for seed tests."""
    engine = get_engine(f"sqlite:///{tmp_path / 'seed.db'}")
    init_db(engine)
    factory = create_session_factory(engine)
    with factory() as session:
        yield session


# Reusable synthetic-lead fixtures (role-only POCs, fictional companies).
@pytest.fixture
def hot_lead():
    return synthetic_leads.hot_lead()


@pytest.fixture
def warm_lead():
    return synthetic_leads.warm_lead()


@pytest.fixture
def nurture_lead():
    return synthetic_leads.nurture_lead()


@pytest.fixture
def low_lead():
    return synthetic_leads.low_lead()


@pytest.fixture
def project_lead():
    return synthetic_leads.project_lead()


@pytest.fixture
def hiring_lead():
    return synthetic_leads.hiring_lead()


@pytest.fixture
def vendor_lead():
    return synthetic_leads.vendor_lead()


@pytest.fixture
def digital_transformation_lead():
    return synthetic_leads.digital_transformation_lead()


@pytest.fixture
def missing_data_lead():
    return synthetic_leads.missing_data_lead()
