"""API tests for provenance filtering and the technology-demand endpoint."""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import sessionmaker

import api.main
from api.dependencies import get_session
from collectors.raw_record import RawRecordDraft
from database.models import DataProvenance, LeadPriority
from database.raw_repository import create_raw_record_from_draft
from database.repository import create_lead, get_engine, init_db

NOW = datetime(2026, 9, 5)


@pytest.fixture
def seeded_client(tmp_path):
    engine = get_engine(f"sqlite:///{tmp_path / 'prov.db'}")
    init_db(engine)
    factory = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)

    with factory() as s:
        create_lead(
            s, company_name="Real Co", normalized_company_name="real co",
            data_provenance=DataProvenance.REAL, it_job_count=30, lead_score=90.0,
            lead_priority=LeadPriority.HOT, technologies=["Java"],
        )
        create_lead(
            s, company_name="Demo Co", normalized_company_name="demo co",
            data_provenance=DataProvenance.SYNTHETIC, it_job_count=20, lead_score=85.0,
            lead_priority=LeadPriority.HOT, technologies=["Python"],
        )
        for i in range(4):
            create_raw_record_from_draft(s, RawRecordDraft(
                source_id="adzuna", external_id=f"r{i}", record_type="JOB_POSTING",
                title=f"Java Developer {i}", company_name="Real Co",
                technologies=["Java", "AWS"], is_synthetic=False,
                published_at=NOW - timedelta(days=2),
            ))
        create_raw_record_from_draft(s, RawRecordDraft(
            source_id="demo_jobs", external_id="d0", record_type="JOB_POSTING",
            title="Python Developer", company_name="Demo Co",
            technologies=["Python"], is_synthetic=True, published_at=NOW - timedelta(days=2),
        ))

    def override():
        session = factory()
        try:
            yield session
        finally:
            session.close()

    api.main.app.dependency_overrides[get_session] = override
    yield TestClient(api.main.app)
    api.main.app.dependency_overrides.clear()


def test_provenance_real_only(seeded_client):
    items = seeded_client.get("/leads", params={"provenance": "real"}).json()["items"]
    names = {i["company_name"] for i in items}
    assert names == {"Real Co"}
    assert items[0]["data_provenance"] == "REAL"


def test_provenance_synthetic_only(seeded_client):
    items = seeded_client.get("/leads", params={"provenance": "synthetic"}).json()["items"]
    assert {i["company_name"] for i in items} == {"Demo Co"}


def test_provenance_all(seeded_client):
    items = seeded_client.get("/leads", params={"provenance": "all"}).json()["items"]
    assert {i["company_name"] for i in items} == {"Real Co", "Demo Co"}


def test_company_fields_present_in_response(seeded_client):
    item = seeded_client.get("/leads", params={"provenance": "real"}).json()["items"][0]
    for key in ("it_job_count", "recent_job_count", "source_count", "hiring_intensity",
                "primary_target_role", "company_signals", "evidence", "data_provenance"):
        assert key in item


def test_technology_demand_real(seeded_client):
    data = seeded_client.get("/leads/technology-demand", params={"provenance": "real"}).json()
    demand = {d["technology"]: d for d in data["items"]}
    assert demand["Java"]["openings"] == 4
    assert demand["Java"]["companies"] == 1
    assert "Python" not in demand  # synthetic excluded


def test_technology_demand_synthetic(seeded_client):
    data = seeded_client.get("/leads/technology-demand", params={"provenance": "synthetic"}).json()
    assert {d["technology"] for d in data["items"]} == {"Python"}
