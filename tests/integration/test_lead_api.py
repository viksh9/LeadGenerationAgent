"""Integration tests for the FastAPI Lead API layer.

Each test uses a dedicated throwaway SQLite database via a dependency override,
so the real development database is never touched.
"""

from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import sessionmaker

import api.main
from api.dependencies import get_session
from database.repository import get_engine, init_db

RECENT_ISO = (datetime.now(timezone.utc) - timedelta(days=2)).isoformat()

ANALYZE_LEAD = {
    "company_name": "NorthStar Banking Technologies",
    "industry": "BFSI",
    "signal_title": "Digital Banking Transformation",
    "signal_description": (
        "The company recently won a major banking modernization project and is hiring "
        "30 Java engineers, 10 AWS engineers and 5 DevOps specialists."
    ),
    "technologies": ["Java", "Spring Boot", "AWS", "DevOps"],
    "estimated_hiring": 45,
    "signal_date": RECENT_ISO,
    "poc_name": "Priya Raman",
    "poc_title": "VP of Engineering",
    "source_url": "https://news.example/northstar",
}


@pytest.fixture
def client(tmp_path):
    engine = get_engine(f"sqlite:///{tmp_path / 'api.db'}")
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


def _create(client, **overrides):
    body = {"company_name": "Acme Corp", "industry": "IT", "location": "Pune"}
    body.update(overrides)
    return client.post("/leads", json=body)


# 1 health ------------------------------------------------------------------
def test_health(client):
    resp = client.get("/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "healthy"
    assert body["app"] and body["version"]


# 2 create ------------------------------------------------------------------
def test_create_lead(client):
    resp = _create(client, company_name="Beta Ltd")
    assert resp.status_code == 201
    body = resp.json()
    assert body["id"] > 0
    assert body["company_name"] == "Beta Ltd"
    assert body["lead_priority"] == "LOW"  # not calculated on direct create
    assert body["status"] == "NEW"


# 3 + 21 analyze end-to-end -------------------------------------------------
def test_analyze_endpoint_end_to_end(client):
    resp = client.post("/leads/analyze", json=ANALYZE_LEAD)
    assert resp.status_code == 201
    body = resp.json()
    assert body["lead_id"] and body["lead_id"] > 0
    assert 0 <= body["final_score"] <= 100
    assert body["priority"] in {"HOT", "WARM", "NURTURE", "LOW"}
    assert {"PROJECT_AWARD", "HIRING", "DIGITAL_TRANSFORMATION"}.issubset(
        set(body["signal_analysis"]["signal_types"])
    )
    assert body["opportunity_analysis"]["opportunity_type"] != "LOW_CONFIDENCE"
    assert body["poc_recommendation"]["primary_role"]["role"]
    assert body["pitch_result"]["email_subject"]
    # persisted and retrievable
    detail = client.get(f"/leads/{body['lead_id']}")
    assert detail.status_code == 200
    assert detail.json()["company_name"] == "NorthStar Banking Technologies"


def test_analyze_reanalysis_returns_200(client):
    first = client.post("/leads/analyze", json=ANALYZE_LEAD)
    second = client.post("/leads/analyze", json=ANALYZE_LEAD)
    assert first.status_code == 201
    assert second.status_code == 200  # existing lead re-analyzed
    assert first.json()["lead_id"] == second.json()["lead_id"]


# 4 list --------------------------------------------------------------------
def test_list_leads(client):
    _create(client, company_name="A")
    _create(client, company_name="B")
    resp = client.get("/leads")
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 2
    assert body["page"] == 1 and body["page_size"] == 20
    assert len(body["items"]) == 2


# 5 get ---------------------------------------------------------------------
def test_get_lead(client):
    lead_id = _create(client).json()["id"]
    resp = client.get(f"/leads/{lead_id}")
    assert resp.status_code == 200
    assert resp.json()["id"] == lead_id


# 6 update ------------------------------------------------------------------
def test_update_lead(client):
    lead_id = _create(client).json()["id"]
    resp = client.put(f"/leads/{lead_id}", json={"location": "Bengaluru", "status": "CONTACTED"})
    assert resp.status_code == 200
    assert resp.json()["location"] == "Bengaluru"
    assert resp.json()["status"] == "CONTACTED"


def test_update_cannot_set_calculated_fields(client):
    lead_id = _create(client).json()["id"]
    resp = client.put(f"/leads/{lead_id}", json={"lead_score": 99})
    assert resp.status_code == 422  # forbidden field


# 7 delete ------------------------------------------------------------------
def test_delete_lead(client):
    lead_id = _create(client).json()["id"]
    assert client.delete(f"/leads/{lead_id}").status_code == 204
    assert client.get(f"/leads/{lead_id}").status_code == 404


# 8 404 ---------------------------------------------------------------------
def test_get_missing_lead_returns_404(client):
    resp = client.get("/leads/999999")
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "not_found"


def test_delete_missing_lead_returns_404(client):
    assert client.delete("/leads/999999").status_code == 404


# 9-12 validation -----------------------------------------------------------
def test_invalid_payload_missing_company_name(client):
    assert client.post("/leads", json={"industry": "IT"}).status_code == 422


def test_invalid_url(client):
    assert _create(client, source_url="not-a-url").status_code == 422


def test_invalid_score_on_analyze_is_ignored_not_error(client):
    # LeadAnalyzeRequest ignores calculated fields; score is computed.
    resp = client.post("/leads/analyze", json={"company_name": "X", "lead_score": 9999, "signal_description": "hiring engineers"})
    assert resp.status_code in {200, 201}
    assert 0 <= resp.json()["final_score"] <= 100


def test_negative_hiring_value(client):
    assert _create(client, estimated_hiring=-5).status_code == 422


def test_negative_project_value(client):
    assert _create(client, project_value=-1).status_code == 422


# 13 pagination -------------------------------------------------------------
def test_pagination(client):
    for i in range(5):
        _create(client, company_name=f"C{i}")
    resp = client.get("/leads?page=1&page_size=2")
    body = resp.json()
    assert body["total"] == 5
    assert body["page_size"] == 2
    assert body["total_pages"] == 3
    assert len(body["items"]) == 2


def test_invalid_pagination_values(client):
    assert client.get("/leads?page=0").status_code == 422
    assert client.get("/leads?page_size=0").status_code == 422
    assert client.get("/leads?page_size=101").status_code == 422


# 14 search -----------------------------------------------------------------
def test_search(client):
    _create(client, company_name="Alpha Bank")
    _create(client, company_name="Beta Retail")
    resp = client.get("/leads?search=alpha")
    assert resp.json()["total"] == 1
    assert resp.json()["items"][0]["company_name"] == "Alpha Bank"


# 15-19 filters -------------------------------------------------------------
def test_industry_filter(client):
    _create(client, company_name="A", industry="BFSI")
    _create(client, company_name="B", industry="Healthcare")
    resp = client.get("/leads?industry=BFSI")
    assert resp.json()["total"] == 1


def test_priority_filter_uses_analyzed_lead(client):
    client.post("/leads/analyze", json=ANALYZE_LEAD)
    resp = client.get("/leads?lead_priority=HOT")
    assert resp.json()["total"] >= 1


def test_status_filter(client):
    lead_id = _create(client).json()["id"]
    client.put(f"/leads/{lead_id}", json={"status": "QUALIFIED"})
    assert client.get("/leads?status=QUALIFIED").json()["total"] == 1
    assert client.get("/leads?status=NEW").json()["total"] == 0


def test_score_filtering(client):
    client.post("/leads/analyze", json=ANALYZE_LEAD)  # HOT, high score
    _create(client, company_name="Low")  # score 0
    assert client.get("/leads?min_score=80").json()["total"] >= 1
    assert client.get("/leads?max_score=10").json()["total"] >= 1


def test_technology_filtering(client):
    client.post("/leads/analyze", json=ANALYZE_LEAD)
    resp = client.get("/leads?technology=Java")
    assert resp.json()["total"] >= 1
    assert client.get("/leads?technology=Cobol").json()["total"] == 0


# 20 sorting ----------------------------------------------------------------
def test_sorting(client):
    _create(client, company_name="Zeta")
    _create(client, company_name="Alpha")
    asc = client.get("/leads?sort_by=company_name&sort_order=asc").json()["items"]
    assert asc[0]["company_name"] == "Alpha"
    desc = client.get("/leads?sort_by=company_name&sort_order=desc").json()["items"]
    assert desc[0]["company_name"] == "Zeta"


def test_invalid_sort_field_rejected(client):
    assert client.get("/leads?sort_by=drop_table").status_code == 422


# 21 combined filters -------------------------------------------------------
def test_combined_filters(client):
    client.post("/leads/analyze", json=ANALYZE_LEAD)
    resp = client.get("/leads?industry=BFSI&lead_priority=HOT&min_score=80")
    assert resp.status_code == 200
    assert resp.json()["total"] >= 1


# 24 duplicate handling -----------------------------------------------------
def test_duplicate_handling_on_analyze(client):
    a = client.post("/leads/analyze", json=ANALYZE_LEAD)
    b = client.post("/leads/analyze", json=ANALYZE_LEAD)
    assert a.json()["lead_id"] == b.json()["lead_id"]
    assert client.get("/leads").json()["total"] == 1  # not duplicated


# 25 CORS -------------------------------------------------------------------
def test_cors_configuration(client):
    resp = client.get("/health", headers={"origin": "http://localhost:5173"})
    assert resp.headers.get("access-control-allow-origin") == "http://localhost:5173"


# docs ----------------------------------------------------------------------
def test_openapi_docs_available(client):
    assert client.get("/openapi.json").status_code == 200
    assert client.get("/docs").status_code == 200
