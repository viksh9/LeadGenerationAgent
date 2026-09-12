"""Scheduled ATS collection + source-inventory DB-awareness (offline).

Verifies the CAREER_SOURCE_COLLECTION handler collects DB-registered boards (no env
needed) and folds real jobs into leads, and that the source inventory reports a
DB-registered ATS board as CONFIGURED/CONNECTED. The Greenhouse HTTP layer is mocked
(httpx.MockTransport) — no real network.
"""

from __future__ import annotations

from datetime import datetime

import httpx

from app.source_inventory import source_inventory
from collectors.ats import greenhouse as gh
from collectors.career_source_registry import register_career_source
from collectors.source_registry import SourceCategory, SourceDefinition, SourceType
from database.models import AtsProvider, CareerSourceStatus, Company, JobType, Lead, ScheduledJob, utcnow
from scheduler.handlers import handle_career_source_collection
from scheduler.errors import SkipJob

NOW = datetime(2026, 9, 13, 2, 0, 0)

_GH_PAYLOAD = {
    "meta": {"total": 2},
    "jobs": [
        {"id": 11, "title": "Senior Backend Engineer (Python)", "updated_at": "2026-09-01T10:00:00Z",
         "location": {"name": "Bengaluru, Karnataka, India"},
         "absolute_url": "https://boards.greenhouse.io/acme/jobs/11", "company_name": "Acme Labs",
         "content": "Build Python + AWS services."},
        {"id": 12, "title": "Frontend Engineer (React)", "updated_at": "2026-09-01T10:00:00Z",
         "location": {"name": "San Francisco, California, United States"},
         "absolute_url": "https://boards.greenhouse.io/acme/jobs/12", "company_name": "Acme Labs",
         "content": "React + TypeScript."},
    ],
}


def _mock_greenhouse_builder(monkeypatch):
    """Patch the ATS builder so it returns a Greenhouse collector on a mock transport."""
    def _build(self, board_identifier):
        cfg = gh.GreenhouseConfig(boards=[board_identifier])   # india_only=True by default
        client = gh.GreenhouseClient(cfg, http=httpx.Client(
            transport=httpx.MockTransport(lambda r: httpx.Response(200, json=_GH_PAYLOAD))))
        src = SourceDefinition(source_id="greenhouse", name="greenhouse",
                               category=SourceCategory.COMPANY, source_type=SourceType.PUBLIC_WEB)
        return gh.GreenhouseCollector(src, config=cfg, client=client)
    from collectors.company.ats import GreenhouseATSProvider
    monkeypatch.setattr(GreenhouseATSProvider, "build_collector", _build)


def _job():
    return ScheduledJob(job_name="collect:career-sources",
                        job_type=JobType.CAREER_SOURCE_COLLECTION, interval_seconds=21600)


def test_handler_skips_when_no_enabled_boards(seed_session):
    try:
        handle_career_source_collection(seed_session, _job(), NOW)
        assert False, "expected SkipJob"
    except SkipJob:
        pass


def test_handler_collects_registered_board_india_only(seed_session, monkeypatch):
    _mock_greenhouse_builder(monkeypatch)
    register_career_source(seed_session, ats_provider=AtsProvider.GREENHOUSE,
                           board_identifier="acme", status=CareerSourceStatus.CONNECTED,
                           company_name="Acme Labs")
    seed_session.commit()

    res = handle_career_source_collection(seed_session, _job(), NOW)
    seed_session.commit()

    assert res["notes"]["boards_collected"] == 1
    assert res["notes"]["errors"] == 0
    # India-first: only the Bengaluru role is ingested (the SF role is filtered out),
    # and it folds into a real company-level lead.
    assert res["notes"]["records_accepted"] == 1
    company = seed_session.query(Company).filter(Company.normalized_name.like("acme%")).first()
    assert company is not None
    assert seed_session.query(Lead).count() >= 1


def test_source_inventory_reports_registered_ats_board(seed_session):
    register_career_source(seed_session, ats_provider=AtsProvider.GREENHOUSE,
                           board_identifier="acme", status=CareerSourceStatus.CONNECTED,
                           company_name="Acme Labs")
    seed_session.commit()
    inv = {row["source_id"]: row for row in source_inventory(seed_session)}
    gh_row = inv["greenhouse"]
    assert gh_row["configuration_status"] == "CONFIGURED"       # DB board, not env
    assert gh_row["connection_status"] == "CONNECTED"           # board had a real success
    # Lever has no registered board -> stays honest.
    assert inv["lever"]["configuration_status"] != "CONFIGURED"


def test_sources_endpoint_reflects_wired_ats_board(client):
    """The dashboard's /sources feed must show a DB-registered Greenhouse board as
    CONFIGURED/CONNECTED (updates as boards are wired), not env-only DISCOVERY_REQUIRED."""
    import api.main
    from api.dependencies import get_session
    session = next(api.main.app.dependency_overrides[get_session]())
    register_career_source(session, ats_provider=AtsProvider.GREENHOUSE, board_identifier="acme",
                           status=CareerSourceStatus.CONNECTED, company_name="Acme Labs")
    session.commit()
    session.close()

    body = client.get("/sources").json()
    gh = next(i for i in body["items"] if i["source_id"] == "greenhouse")
    assert gh["status"] == "CONFIGURED"
    assert gh["connection_status"] == "CONNECTED"
    assert "board(s) wired" in (gh.get("detail") or "")
    # Lever has no board -> unaffected.
    lever = next(i for i in body["items"] if i["source_id"] == "lever")
    assert lever["status"] != "CONFIGURED"
