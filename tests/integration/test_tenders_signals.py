"""Tender pipeline, commercial intent, company timeline, and signals/tenders APIs.

Offline: raw TENDER records are ingested into isolated per-test databases; no
external network. Verifies real-only behavior (NULL when the source omits a value,
status from source/closing-date, idempotency, history), intent classification, the
timeline, and the API surfaces.
"""

from __future__ import annotations

from datetime import datetime, timedelta

import api.main
from api.dependencies import get_session
from collectors.raw_record import RawRecordDraft, normalize_company_name
from database.models import CommercialIntent, DataProvenance, TenderRecord, TenderStatus
from database.raw_repository import create_raw_record_from_draft
from ingestion.business_pipeline import run_business_pipeline
from ingestion.tender_pipeline import run_tender_pipeline
from intelligence.commercial_intent import IntentInputs, classify_commercial_intent
from intelligence.company_timeline import build_company_timeline

NOW = datetime(2026, 9, 7)


def _tender_draft(ext, *, closing_days=20, status="open", value=None, currency=None,
                  title="AWS cloud migration RFP", org="Dept of IT Karnataka"):
    payload = {"status": status}
    if closing_days is not None:
        payload["closing_date"] = (NOW + timedelta(days=closing_days)).isoformat()
    if value is not None:
        payload["estimated_value"] = value
        payload["currency"] = currency
    return RawRecordDraft(
        source_id="government_open_data", external_id=ext, record_type="TENDER",
        source_url=f"https://data.gov.in/t/{ext}", title=title,
        description="DevOps and Kubernetes implementation; Java/Spring modernization.",
        company_name=org, location="Bengaluru", published_at=NOW - timedelta(days=2),
        raw_payload=payload, is_synthetic=False,
    )


# --------------------------------------------------------------------------- #
# Tender pipeline
# --------------------------------------------------------------------------- #
def test_tender_normalized_from_real_fields(seed_session):
    create_raw_record_from_draft(seed_session, _tender_draft("T1", value=5_000_000, currency="INR"))
    seed_session.commit()
    run_business_pipeline(seed_session, provenance=DataProvenance.REAL, now=NOW)
    summary = run_tender_pipeline(seed_session, provenance=DataProvenance.REAL, now=NOW)
    assert summary.created == 1
    t = seed_session.query(TenderRecord).one()
    assert t.tender_status is TenderStatus.OPEN            # closing 20 days out
    assert set(t.technologies) >= {"AWS", "Kubernetes", "DevOps"}
    assert t.estimated_value == 5_000_000 and t.currency == "INR"
    assert t.freshness_score > 0
    assert t.data_provenance is DataProvenance.REAL
    assert t.business_signal_id is not None                # linked to its BusinessSignal


def test_tender_value_null_when_source_omits(seed_session):
    create_raw_record_from_draft(seed_session, _tender_draft("T2"))     # no value
    seed_session.commit()
    run_tender_pipeline(seed_session, provenance=DataProvenance.REAL, now=NOW)
    t = seed_session.query(TenderRecord).one()
    assert t.estimated_value is None                       # never fabricated
    assert t.currency is None


def test_tender_status_from_closing_date(seed_session):
    create_raw_record_from_draft(seed_session, _tender_draft("closed", status="", closing_days=-5))
    create_raw_record_from_draft(seed_session, _tender_draft("soon", status="", closing_days=3))
    seed_session.commit()
    run_tender_pipeline(seed_session, provenance=DataProvenance.REAL, now=NOW)
    by_ext = {t.source_record_id: t for t in seed_session.query(TenderRecord).all()}
    assert by_ext["closed"].tender_status is TenderStatus.CLOSED
    assert by_ext["soon"].tender_status is TenderStatus.CLOSING_SOON


def test_tender_status_cancelled_from_source(seed_session):
    create_raw_record_from_draft(seed_session, _tender_draft("x", status="cancelled"))
    seed_session.commit()
    run_tender_pipeline(seed_session, provenance=DataProvenance.REAL, now=NOW)
    assert seed_session.query(TenderRecord).one().tender_status is TenderStatus.CANCELLED


def test_tender_ingestion_idempotent(seed_session):
    create_raw_record_from_draft(seed_session, _tender_draft("T3"))
    seed_session.commit()
    run_tender_pipeline(seed_session, provenance=DataProvenance.REAL, now=NOW)
    second = run_tender_pipeline(seed_session, provenance=DataProvenance.REAL, now=NOW)
    assert second.created == 0 and second.updated == 1     # upsert, no duplicate
    assert seed_session.query(TenderRecord).count() == 1


# --------------------------------------------------------------------------- #
# Commercial intent
# --------------------------------------------------------------------------- #
def test_intent_unknown_without_evidence():
    r = classify_commercial_intent(IntentInputs())
    assert r.intent is CommercialIntent.UNKNOWN


def test_intent_scales_with_evidence():
    strong = classify_commercial_intent(IntentInputs(
        evidence_confidence=90, is_fresh=True, has_project_or_tender=True,
        has_vendor_or_award=True, active_it_jobs=15, distinct_signal_types=3,
        technology_relevant=True, company_resolved=True))
    weak = classify_commercial_intent(IntentInputs(
        evidence_confidence=30, is_fresh=False, has_project_or_tender=True,
        active_it_jobs=1, company_resolved=False))
    assert strong.intent in (CommercialIntent.VERY_HIGH, CommercialIntent.HIGH)
    assert weak.intent in (CommercialIntent.LOW, CommercialIntent.MEDIUM)
    # Intent is a separate axis — the strong case outranks the weak one.
    assert strong.score > weak.score


# --------------------------------------------------------------------------- #
# Timeline
# --------------------------------------------------------------------------- #
def test_company_timeline_merges_events(seed_session):
    create_raw_record_from_draft(seed_session, _tender_draft("T4", org="Acme Tech"))
    seed_session.commit()
    run_business_pipeline(seed_session, provenance=DataProvenance.REAL, now=NOW)
    run_tender_pipeline(seed_session, provenance=DataProvenance.REAL, now=NOW)
    events = build_company_timeline(seed_session, normalized_name=normalize_company_name("Acme Tech"))
    cats = {e.category for e in events}
    assert "TENDER" in cats and "SIGNAL" in cats           # distinct related events
    assert all(e.title for e in events)


# --------------------------------------------------------------------------- #
# APIs
# --------------------------------------------------------------------------- #
def test_signals_and_tenders_empty_states(client):
    assert client.get("/signals").json()["total"] == 0
    assert client.get("/tenders").json()["total"] == 0


def test_tenders_api_populated_and_filtered(client):
    session = next(api.main.app.dependency_overrides[get_session]())
    create_raw_record_from_draft(session, _tender_draft("A1", value=1_000_000, currency="INR"))
    session.commit()
    run_business_pipeline(session, provenance=DataProvenance.REAL, now=NOW)
    run_tender_pipeline(session, provenance=DataProvenance.REAL, now=NOW)
    session.close()

    body = client.get("/tenders").json()
    assert body["total"] == 1
    t = body["items"][0]
    assert t["tender_status"] == "OPEN" and t["estimated_value"] == 1_000_000
    assert "AWS" in t["technologies"]
    assert client.get("/tenders?status=OPEN").json()["total"] == 1
    assert client.get("/tenders?status=CLOSED").json()["total"] == 0
    assert client.get("/tenders?technology=aws").json()["total"] == 1
    assert client.get("/signals?signal_type=TENDER").json()["total"] == 1


def test_tender_404(client):
    assert client.get("/tenders/99999").status_code == 404
    assert client.get("/signals/99999").status_code == 404
