"""Integration tests: raw job records -> company-level leads (with provenance)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from collectors.raw_record import RawRecordDraft
from database.models import DataProvenance, Lead
from database.raw_repository import create_raw_record_from_draft
from database.repository import query_leads
from intelligence.company_pipeline import rebuild_company_leads

NOW = datetime(2026, 9, 5)


def _raw(session, company, title, techs, *, days_ago=3, city="Bengaluru", source="adzuna", ext=None, synthetic=False):
    draft = RawRecordDraft(
        source_id=source, external_id=ext or f"{title}-{days_ago}",
        source_url=f"https://x/{ext or title}",
        published_at=NOW - timedelta(days=days_ago),
        record_type="JOB_POSTING", title=title, description=f"{title}. {' '.join(techs)}",
        company_name=company, location=f"{city}, IN", industry="Software",
        technologies=list(techs), is_synthetic=synthetic,
    )
    return create_raw_record_from_draft(session, draft)


def test_rebuild_creates_one_lead_per_company(seed_session):
    for i in range(12):
        _raw(seed_session, "Ravi Technologies Pvt Ltd", f"Java Developer {i}", ["Java", "AWS"], ext=f"j{i}")
    for i in range(3):
        _raw(seed_session, "Tiny Co", f"Software Engineer {i}", ["Java"], days_ago=100, ext=f"t{i}")

    summary = rebuild_company_leads(seed_session, provenance=DataProvenance.REAL, now=NOW)
    assert summary.companies == 2
    assert summary.created == 2

    leads, total = query_leads(seed_session, provenance=DataProvenance.REAL, page_size=10)
    assert total == 2
    ravi = next(l for l in leads if l.company_name.startswith("Ravi"))
    assert ravi.it_job_count == 12
    assert ravi.data_provenance is DataProvenance.REAL
    assert ravi.source_count == 1
    assert ravi.evidence and len(ravi.evidence) >= 12
    assert ravi.lead_priority.value in {"HOT", "WARM", "NURTURE", "LOW"}


def test_rebuild_is_idempotent_upsert(seed_session):
    for i in range(6):
        _raw(seed_session, "Ravi Technologies", f"Java Developer {i}", ["Java"], ext=f"j{i}")
    first = rebuild_company_leads(seed_session, provenance=DataProvenance.REAL, now=NOW)
    second = rebuild_company_leads(seed_session, provenance=DataProvenance.REAL, now=NOW)
    assert first.created == 1
    assert second.created == 0 and second.updated == 1
    assert seed_session.query(Lead).count() == 1


def test_real_and_synthetic_kept_separate(seed_session):
    for i in range(5):
        _raw(seed_session, "Ravi Technologies", f"Java Developer {i}", ["Java"], ext=f"r{i}", synthetic=False)
    for i in range(5):
        _raw(seed_session, "Ravi Technologies", f"Java Developer {i}", ["Java"], ext=f"s{i}", source="demo_jobs", synthetic=True)

    rebuild_company_leads(seed_session, provenance=DataProvenance.REAL, now=NOW)
    rebuild_company_leads(seed_session, provenance=DataProvenance.SYNTHETIC, now=NOW)

    real, real_total = query_leads(seed_session, provenance=DataProvenance.REAL, page_size=10)
    synth, synth_total = query_leads(seed_session, provenance=DataProvenance.SYNTHETIC, page_size=10)
    assert real_total == 1 and synth_total == 1
    assert real[0].data_provenance is DataProvenance.REAL
    assert synth[0].data_provenance is DataProvenance.SYNTHETIC
    # A real company lead is never built from synthetic jobs.
    assert real[0].it_job_count == 5


def test_cross_source_confirmation_sets_source_count(seed_session):
    _raw(seed_session, "Ravi Technologies", "Java Developer", ["Java"], city="Pune", source="adzuna", ext="a1")
    _raw(seed_session, "Ravi Technologies", "Java Developer", ["Java"], city="Pune", source="company_career", ext="c1")
    rebuild_company_leads(seed_session, provenance=DataProvenance.REAL, now=NOW)
    leads, _ = query_leads(seed_session, provenance=DataProvenance.REAL, page_size=10)
    assert leads[0].it_job_count == 1
    assert leads[0].source_count == 2


def test_location_lists_real_cities_dropping_country_and_plus_n():
    """Location shows the full explicit city list (most-active first), never the bare
    country token or a "+N more" summary (user-facing display requirement)."""
    import types
    from collections import Counter
    from intelligence.company_pipeline import _location, _location_all
    agg = types.SimpleNamespace(cities=Counter({"India": 10, "Bengaluru": 8, "Chennai": 5, "Hyderabad": 3}))
    assert _location(agg) == "Bengaluru, Chennai, Hyderabad"       # country dropped, no "+N more"
    assert _location_all(agg) == "Bengaluru, Chennai, Hyderabad"
    # Two cities -> both shown explicitly.
    two = types.SimpleNamespace(cities=Counter({"Bengaluru": 4, "Chennai": 2}))
    assert _location(two) == "Bengaluru, Chennai"
    # Only the country is known -> keep it (honest; never invent a city).
    only_country = types.SimpleNamespace(cities=Counter({"India": 5}))
    assert _location(only_country) == "India"
    # No location data -> None (honest empty).
    assert _location(types.SimpleNamespace(cities=Counter())) is None
