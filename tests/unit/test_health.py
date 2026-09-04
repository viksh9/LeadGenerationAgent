"""API startup + health-check test."""

from fastapi.testclient import TestClient

from api.main import app


def test_health_endpoint_and_startup():
    # Entering the TestClient context runs the lifespan (startup -> init_db).
    with TestClient(app) as client:
        response = client.get("/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "healthy"
    assert body["app"] == "LeadGenerationAgent"
    assert "environment" in body
