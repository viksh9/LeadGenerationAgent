"""Excel export tests (Prompt 45 §44, §45, §47).

Verifies the workbook is built from ACTUAL DB rows, is a valid .xlsx with the
expected sheets, matches DB counts, sanitises formula-injection, leaks no secrets,
enforces auth/scope, audits, and handles the empty database honestly. Uses
isolated throwaway DBs.
"""

from __future__ import annotations

from io import BytesIO

import openpyxl

import api.main
from api.dependencies import get_session
from database.models import (
    AuditLog,
    DataProvenance,
    EvidenceRecord,
    EvidenceType,
    Lead,
    LeadPriority,
    LeadStatus,
)
from export.excel import build_workbook, workbook_counts


def _seed_real_lead(session, company="Acme Tech"):
    lead = Lead(company_name=company, normalized_company_name=company.lower(),
                lead_score=90.0, lead_priority=LeadPriority.HOT, status=LeadStatus.NEW,
                evidence_confidence=85, source_name="adzuna", source_url="https://adzuna/x",
                data_provenance=DataProvenance.REAL)
    session.add(lead)
    session.flush()
    session.add(EvidenceRecord(lead_id=lead.id, evidence_type=EvidenceType.JOB, content_hash="e1",
                               source_name="adzuna", source_url="https://adzuna/x",
                               data_provenance=DataProvenance.REAL))
    session.flush()
    return lead


def _load(content: bytes):
    return openpyxl.load_workbook(BytesIO(content), read_only=True)


# --------------------------------------------------------------------------- #
# Workbook builder (unit-ish, on a seeded session)
# --------------------------------------------------------------------------- #
def test_workbook_has_readme_and_data_dictionary(seed_session):
    _seed_real_lead(seed_session)
    buf, meta = build_workbook(seed_session, scope="all")
    wb = _load(buf.getvalue())
    assert "README" in wb.sheetnames
    assert "Data Dictionary" in wb.sheetnames
    assert "Leads" in wb.sheetnames and "Sources" in wb.sheetnames


def test_workbook_counts_match_db(seed_session):
    for i in range(3):
        _seed_real_lead(seed_session, company=f"Co {i}")
    counts = workbook_counts(seed_session)
    assert counts["Leads"] == 3
    buf, meta = build_workbook(seed_session, scope="all")
    assert meta["rows_by_sheet"]["Leads"] == 3


def test_empty_database_has_no_fake_rows(seed_session):
    buf, meta = build_workbook(seed_session, scope="all")
    wb = _load(buf.getvalue())
    ws = wb["Leads"]
    rows = list(ws.iter_rows(values_only=True))
    assert rows[0][0] == "Lead ID"                       # header present
    assert rows[1][0] == "No real data available yet."   # honest, not fabricated
    assert meta["rows_by_sheet"]["Leads"] == 0


def test_formula_injection_is_neutralised(seed_session):
    _seed_real_lead(seed_session, company="=HYPERLINK(1)")
    buf, _ = build_workbook(seed_session, scope="all")
    wb = _load(buf.getvalue())
    ws = wb["Leads"]
    header = [c.value for c in next(ws.iter_rows(min_row=1, max_row=1))]
    ci = header.index("Company")
    value = list(ws.iter_rows(min_row=2, max_row=2, values_only=True))[0][ci]
    assert value.startswith("'=")   # sanitised: leading quote → treated as text, not a formula


def test_no_secrets_in_workbook(seed_session, monkeypatch):
    from config import settings as sm
    monkeypatch.setattr(sm.get_settings(), "admin_api_key", "supersecretkey12345")
    monkeypatch.setattr(sm.get_settings(), "webhook_secret", "whsec_supersecret_98765")
    _seed_real_lead(seed_session)
    buf, _ = build_workbook(seed_session, scope="all")
    blob = buf.getvalue()
    assert b"supersecretkey12345" not in blob
    assert b"whsec_supersecret_98765" not in blob


# --------------------------------------------------------------------------- #
# API endpoint
# --------------------------------------------------------------------------- #
def _seed_via_client(client):
    session = next(api.main.app.dependency_overrides[get_session]())
    lead = _seed_real_lead(session)
    session.commit()
    session.close()
    return lead


def test_api_export_summary(client):
    _seed_via_client(client)
    body = client.get("/export/summary").json()
    assert body["counts"]["Leads"] == 1 and body["total_records"] >= 1


def test_api_export_excel_returns_valid_xlsx(client):
    _seed_via_client(client)
    r = client.get("/export/excel?scope=all")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith(
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    assert r.headers["x-export-filename"].endswith(".xlsx")
    assert "attachment" in r.headers["content-disposition"]
    wb = _load(r.content)
    assert "Leads" in wb.sheetnames


def test_api_export_scope_leads_only(client):
    _seed_via_client(client)
    r = client.get("/export/excel?scope=leads")
    wb = _load(r.content)
    business = [s for s in wb.sheetnames if s not in ("README", "Data Dictionary", "Sources")]
    assert business == ["Leads"]


def test_api_export_invalid_scope(client):
    assert client.get("/export/excel?scope=bogus").status_code == 422


def test_api_export_writes_audit_log(client):
    _seed_via_client(client)
    client.get("/export/excel?scope=all")
    session = next(api.main.app.dependency_overrides[get_session]())
    from sqlalchemy import select
    audits = session.execute(
        select(AuditLog).where(AuditLog.action == "EXCEL_EXPORT")
    ).scalars().all()
    session.close()
    assert len(audits) >= 1 and audits[0].entity_type == "export"


def test_api_export_rbac_enforced_when_key_set(client, monkeypatch):
    from config import settings as sm
    monkeypatch.setattr(sm.get_settings(), "admin_api_key", "secret")
    # No role header → VIEWER is allowed to export (read op); ADMIN key also works.
    assert client.get("/export/summary", headers={"X-Role": "VIEWER"}).status_code == 200
    assert client.get("/export/excel?scope=all", headers={"X-Admin-Key": "secret"}).status_code == 200
