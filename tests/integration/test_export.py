"""Single-sheet lead export tests (Prompt 47 §36, §37, §38).

Verifies the workbook has EXACTLY one worksheet named "Lead Data" with the exact
16 columns in order, one row per real lead, provenance-filtered, with source-backed
(never guessed) contacts, formula-injection safe, no secrets, and honest empty
state. Isolated throwaway DBs.
"""

from __future__ import annotations

from datetime import timedelta
from io import BytesIO

import openpyxl

import api.main
from api.dependencies import get_session
from database.models import (
    AuditLog,
    ContactType,
    DataProvenance,
    DecisionMaker,
    EmailStatus,
    Lead,
    LeadPriority,
    LeadStatus,
    SignalType,
    VerificationStatus,
    utcnow,
)
from export.excel import HEADERS, SHEET_NAME, build_workbook, workbook_counts
from intelligence.opportunity_view import derive_opportunity_view, opportunity_cell

EXPECTED_HEADERS = [
    "Sr No", "Company Name", "No of Openings", "Location", "Intensity", "Signal",
    "Technology", "Target POC Details", "Score", "Priority", "Status",
    "Contact Number", "Email", "Opportunity", "Signal Date", "Source",
]


def _lead(session, company="Acme Tech", *, provenance=DataProvenance.REAL, score=90.0,
          priority=LeadPriority.HOT, openings=12, company_id=None,
          signal_type=None, estimated_hiring=None, signal_date=None,
          signal_title=None, signal_confidence=None, company_signals=None,
          location="Bengaluru", location_all=None):
    lead = Lead(company_name=company, normalized_company_name=company.lower(), company_id=company_id,
                lead_score=score, lead_priority=priority, status=LeadStatus.NEW,
                it_job_count=openings, location=location, location_all=location_all,
                technologies=["Java", "AWS"],
                primary_target_role="Head of Engineering", opportunity_summary="Cloud staff augmentation",
                signal_type=signal_type, estimated_hiring=estimated_hiring, signal_date=signal_date,
                signal_title=signal_title, signal_confidence=signal_confidence,
                company_signals=company_signals or [],
                source_name="1 source(s): adzuna", source_url="https://adzuna/x",
                data_provenance=provenance)
    session.add(lead)
    session.flush()
    return lead


def _verified_contact(session, company_id, name="Jane Doe"):
    dm = DecisionMaker(company_id=company_id, company_name="Acme Tech", full_name=name,
                       normalized_name=name.lower(), job_title="VP Engineering",
                       normalized_role="vp engineering", business_email="jane@acme.example",
                       business_phone="+91-80-1234-5678", email_status=EmailStatus.VERIFIED_SOURCE,
                       contact_type=ContactType.BUSINESS_EMAIL,
                       verification_status=VerificationStatus.VERIFIED, data_provenance=DataProvenance.REAL)
    session.add(dm)
    session.flush()
    return dm


def _load(content: bytes):
    return openpyxl.load_workbook(BytesIO(content), read_only=True)


# --------------------------------------------------------------------------- #
# Workbook structure (§37)
# --------------------------------------------------------------------------- #
def test_exactly_one_sheet_named_lead_data(seed_session):
    _lead(seed_session)
    wb = _load(build_workbook(seed_session)[0].getvalue())
    assert wb.sheetnames == [SHEET_NAME] == ["Lead Data"]


def test_headers_exact_order(seed_session):
    _lead(seed_session)
    wb = _load(build_workbook(seed_session)[0].getvalue())
    headers = [c.value for c in next(wb[SHEET_NAME].iter_rows(min_row=1, max_row=1))]
    assert headers == EXPECTED_HEADERS == HEADERS


def test_one_row_per_lead_and_srno_sequential(seed_session):
    _lead(seed_session, company="A", score=95)
    _lead(seed_session, company="B", score=80)
    _lead(seed_session, company="C", score=60)
    buf, meta = build_workbook(seed_session)
    assert meta["total_rows"] == 3
    ws = _load(buf.getvalue())[SHEET_NAME]
    data = list(ws.iter_rows(min_row=2, values_only=True))
    assert [r[0] for r in data] == [1, 2, 3]                 # Sr No sequential, not DB id
    assert [r[1] for r in data] == ["A", "B", "C"]           # sorted by score desc


def test_synthetic_leads_excluded(seed_session):
    _lead(seed_session, company="Real", provenance=DataProvenance.REAL)
    _lead(seed_session, company="Fake", provenance=DataProvenance.SYNTHETIC)
    buf, meta = build_workbook(seed_session)
    assert meta["total_rows"] == 1
    assert workbook_counts(seed_session)["Leads"] == 1


# --------------------------------------------------------------------------- #
# Column data (§3)
# --------------------------------------------------------------------------- #
def _row(seed_session):
    wb = _load(build_workbook(seed_session)[0].getvalue())
    ws = wb[SHEET_NAME]
    header = [c.value for c in next(ws.iter_rows(min_row=1, max_row=1))]
    values = list(ws.iter_rows(min_row=2, max_row=2, values_only=True))[0]
    return dict(zip(header, values))


def test_poc_recommended_role_when_no_verified_person(seed_session):
    _lead(seed_session)  # no verified contact
    row = _row(seed_session)
    assert row["Target POC Details"] == "Head of Engineering — Recommended Role"
    assert row["Contact Number"] is None and row["Email"] is None   # blank, never guessed


def test_poc_and_contacts_use_verified_person(seed_session):
    lead = _lead(seed_session, company_id=1)
    _verified_contact(seed_session, company_id=1)
    row = _row(seed_session)
    assert row["Target POC Details"] == "Jane Doe — VP Engineering"
    assert row["Contact Number"] == "+91-80-1234-5678"   # genuine phone kept clean, still safe
    assert row["Email"] == "jane@acme.example"


def test_signal_mirrors_opportunities_tab(seed_session):
    # Readable type + specific title + confidence, exactly like the Opportunities tab.
    # No raw SCREAMING_CASE codes leak into the sheet.
    _lead(seed_session, signal_type=SignalType.HIRING,
          signal_title="High technology hiring — 47 open IT roles", signal_confidence=100.0,
          company_signals=["LARGE_TECH_HIRING", "RAPID_HIRING"])
    cell = _row(seed_session)["Signal"]
    assert cell.split("\n") == [
        "Hiring",
        "High technology hiring — 47 open IT roles",
        "Confidence: 100%",
    ]
    assert "HIRING" not in cell and "LARGE_TECH_HIRING" not in cell   # no raw codes


def test_signal_not_available_when_no_signal(seed_session):
    _lead(seed_session)  # no signal_type/title/confidence
    assert _row(seed_session)["Signal"] == "Not available"


def test_openings_and_score_and_source(seed_session):
    _lead(seed_session, openings=22, score=88.0)
    row = _row(seed_session)
    assert row["No of Openings"] == 22
    assert row["Score"] == 88
    assert row["Source"] == "adzuna"           # cleaned from "1 source(s): adzuna"
    assert row["Priority"] == "HOT" and row["Status"] == "NEW"


def test_blank_openings_when_unknown(seed_session):
    _lead(seed_session, openings=0)
    assert _row(seed_session)["No of Openings"] is None   # blank, not fabricated


def test_location_shows_full_city_list_not_compact(seed_session):
    # Excel gets the full list (location_all); the UI's compact "+N more" is never exported.
    _lead(seed_session, location="Chennai +2 more",
          location_all="Chennai, Hyderabad, Bengaluru")
    assert _row(seed_session)["Location"] == "Chennai, Hyderabad, Bengaluru"


def test_location_falls_back_to_compact_when_no_full_list(seed_session):
    _lead(seed_session, location="Pune", location_all=None)
    assert _row(seed_session)["Location"] == "Pune"


# --------------------------------------------------------------------------- #
# Opportunity column — the opportunity type label, mirrors the Opportunity tab.
# Staffing / Est. Team / Urgency are intentionally NOT included in this cell.
# --------------------------------------------------------------------------- #
def test_opportunity_cell_is_type_label_only(seed_session):
    now = utcnow()
    _lead(seed_session, openings=12, signal_type=SignalType.HIRING,
          estimated_hiring=30, signal_date=now - timedelta(days=3))
    cell = _row(seed_session)["Opportunity"]
    assert cell == "Large-Scale Ramp-Up"   # HIRING + hiring>=25 escalates to ramp-up
    assert "Staffing" not in cell and "Est. Team" not in cell and "Urgency" not in cell


def test_opportunity_cell_matches_tab_derivation(seed_session):
    # The exported cell is exactly the shared derivation used by the Opportunity tab.
    now = utcnow()
    lead = _lead(seed_session, signal_type=SignalType.EXPANSION, estimated_hiring=8,
                 signal_date=now - timedelta(days=45))
    expected = opportunity_cell(derive_opportunity_view(lead, signal_date=lead.signal_date, now=now))
    # build with the same `now` so the derivation is deterministic
    from export.excel import build_workbook as _bw
    wb = _load(_bw(seed_session, now=now)[0].getvalue())
    ws = wb[SHEET_NAME]
    header = [c.value for c in next(ws.iter_rows(min_row=1, max_row=1))]
    cell = dict(zip(header, list(ws.iter_rows(min_row=2, max_row=2, values_only=True))[0]))["Opportunity"]
    assert cell == expected == "Large-Scale Ramp-Up"


def test_opportunity_cell_low_confidence_when_no_signal(seed_session):
    # No signal_type -> Low Confidence type, nothing fabricated.
    _lead(seed_session)
    assert _row(seed_session)["Opportunity"] == "Low Confidence"


# --------------------------------------------------------------------------- #
# Security (§31, §30)
# --------------------------------------------------------------------------- #
def test_formula_injection_neutralised(seed_session):
    _lead(seed_session, company="=cmd|'/c calc'!A1")
    assert _row(seed_session)["Company Name"].startswith("'=")


def test_no_secrets_exported(seed_session, monkeypatch):
    from config import settings as sm
    monkeypatch.setattr(sm.get_settings(), "admin_api_key", "supersecret_admin_999")
    _lead(seed_session)
    blob = build_workbook(seed_session)[0].getvalue()
    assert b"supersecret_admin_999" not in blob


def test_empty_database_no_fake_rows(seed_session):
    buf, meta = build_workbook(seed_session)
    assert meta["total_rows"] == 0
    ws = _load(buf.getvalue())[SHEET_NAME]
    rows = list(ws.iter_rows(values_only=True))
    assert rows[0] == tuple(EXPECTED_HEADERS)
    assert rows[1][0] == "No real lead data available."


# --------------------------------------------------------------------------- #
# API
# --------------------------------------------------------------------------- #
def _seed_via_client(client, **kw):
    session = next(api.main.app.dependency_overrides[get_session]())
    lead = _lead(session, **kw)
    session.commit()
    session.close()
    return lead


def test_api_export_single_sheet(client):
    _seed_via_client(client)
    r = client.get("/export/excel?scope=all")
    assert r.status_code == 200
    assert r.headers["x-export-filename"] == r.headers["x-export-filename"]
    assert "lead_data" in r.headers["x-export-filename"]
    wb = _load(r.content)
    assert wb.sheetnames == ["Lead Data"]


def test_api_export_summary_counts_leads(client):
    _seed_via_client(client, company="A")
    _seed_via_client(client, company="B")
    body = client.get("/export/summary").json()
    assert body["counts"]["Leads"] == 2 and body["total_records"] == 2


def test_api_export_audited(client):
    _seed_via_client(client)
    client.get("/export/excel?scope=all")
    session = next(api.main.app.dependency_overrides[get_session]())
    from sqlalchemy import select
    audits = session.execute(select(AuditLog).where(AuditLog.action == "EXCEL_EXPORT")).scalars().all()
    session.close()
    assert len(audits) >= 1


def test_api_export_rbac_enforced_when_key_set(client, monkeypatch):
    from config import settings as sm
    monkeypatch.setattr(sm.get_settings(), "admin_api_key", "secret")
    assert client.get("/export/excel?scope=all").status_code == 403          # no role
    assert client.get("/export/excel?scope=all", headers={"X-Admin-Key": "secret"}).status_code == 200
