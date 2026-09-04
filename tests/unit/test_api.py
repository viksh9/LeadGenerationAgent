from fastapi.testclient import TestClient
from sqlalchemy.orm import sessionmaker

from api.main import app, get_session
from database.repository import get_engine, init_db


def test_health_and_pipeline_run(tmp_path, monkeypatch):
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
    monkeypatch.setattr("api.main.SessionFactory", factory)
    monkeypatch.setattr("processors.pipeline.create_session_factory", lambda: factory)

    client = TestClient(app)
    health = client.get("/health")
    assert health.json()["status"] == "ok"
    assert "environment" in health.json()

    response = client.post("/pipeline/run")
    assert response.status_code == 200
    body = response.json()
    assert body["processed"] >= 1
    assert body["leads"][0]["score"] >= 0

    listed = client.get("/leads")
    assert listed.status_code == 200
    assert len(listed.json()) >= 1

    lead_id = listed.json()[0]["id"]
    detail = client.get(f"/leads/{lead_id}")
    assert detail.status_code == 200
    assert detail.json()["company"]["name"]
    app.dependency_overrides.clear()
