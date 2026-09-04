from pathlib import Path

import pytest

from collectors.json_collector import JsonFileCollector
from config.exceptions import CollectorError
from fastapi.testclient import TestClient
from sqlalchemy.orm import sessionmaker

from api.main import app, get_session
from database.repository import get_engine, init_db


def test_json_collector_missing_file(tmp_path: Path) -> None:
    missing = tmp_path / "does-not-exist.json"
    with pytest.raises(CollectorError):
        JsonFileCollector(missing).collect()


def test_json_collector_invalid_json(tmp_path: Path) -> None:
    bad = tmp_path / "bad.json"
    bad.write_text("{not-json", encoding="utf-8")
    with pytest.raises(CollectorError):
        JsonFileCollector(bad).collect()


def test_lead_not_found_returns_typed_error(tmp_path: Path) -> None:
    engine = get_engine(f"sqlite:///{tmp_path / 'test.db'}")
    init_db(engine)
    factory = sessionmaker(bind=engine, autoflush=False, autocommit=False)

    def override_session():
        session = factory()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_session] = override_session
    client = TestClient(app)
    response = client.get("/leads/99999")
    assert response.status_code == 404
    body = response.json()
    assert body["error"]["code"] == "not_found"
    app.dependency_overrides.clear()
