"""Integration tests: raw business records -> BusinessSignals -> candidates."""

from __future__ import annotations

from datetime import datetime, timedelta

from collectors.raw_record import RawRecordDraft
from database.models import (
    BusinessSignal,
    DataProvenance,
    OpportunityCandidate,
    OpportunityStatus,
    ResolutionStatus,
    SourceRole,
)
from database.raw_repository import create_raw_record_from_draft
from ingestion.business_pipeline import build_business_signals, run_business_pipeline
from ingestion.job_pipeline import build_job_records
from sqlalchemy import func, select

NOW = datetime(2026, 9, 5)


def _news(session, *, title, company="Infosys", source="rss_news", ext, days_ago=3,
          desc="cloud and AWS program", synthetic=False):
    return create_raw_record_from_draft(session, RawRecordDraft(
        source_id=source, external_id=ext, source_url=f"https://x/{ext}",
        published_at=NOW - timedelta(days=days_ago), record_type="NEWS_ARTICLE",
        title=title, description=desc, company_name=company, is_synthetic=synthetic,
    ))


def _job(session, company, ext, *, techs=("Java", "AWS"), days_ago=3):
    return create_raw_record_from_draft(session, RawRecordDraft(
        source_id="adzuna", external_id=ext, record_type="JOB_POSTING",
        title="Senior Java Developer", company_name=company, location="Bengaluru, India",
        technologies=list(techs), published_at=NOW - timedelta(days=days_ago),
    ))


def _count(session, model):
    return session.scalar(select(func.count()).select_from(model))


def test_creates_business_signal(seed_session):
    _news(seed_session, title="Infosys wins digital transformation contract", ext="n1")
    summary = build_business_signals(seed_session, provenance=DataProvenance.REAL, now=NOW)
    assert summary.created == 1
    sig = seed_session.scalars(select(BusinessSignal)).first()
    assert sig.normalized_company_name == "infosys"
    assert sig.resolution_status is ResolutionStatus.RESOLVED
    assert sig.source_references[0].source_role is SourceRole.PRIMARY
    assert sig.evidence_confidence > 0


def test_cross_source_event_dedup(seed_session):
    # Same event (company + type + day) from two different sources -> one signal.
    _news(seed_session, title="Infosys wins digital transformation contract", source="rss_news", ext="a")
    _news(seed_session, title="Infosys digital transformation program confirmed",
          source="company_newsroom", ext="b")
    build_business_signals(seed_session, provenance=DataProvenance.REAL, now=NOW)
    assert _count(seed_session, BusinessSignal) == 1
    sig = seed_session.scalars(select(BusinessSignal)).first()
    assert sig.source_count == 2
    roles = {r.source_role for r in sig.source_references}
    assert SourceRole.PRIMARY in roles and SourceRole.SUPPORTING in roles


def test_duplicate_same_source_not_double_counted(seed_session):
    _news(seed_session, title="Infosys wins digital transformation contract", ext="dup")
    build_business_signals(seed_session, provenance=DataProvenance.REAL, now=NOW)
    build_business_signals(seed_session, provenance=DataProvenance.REAL, now=NOW)  # rerun
    assert _count(seed_session, BusinessSignal) == 1


def test_missing_company_flagged_review(seed_session):
    _news(seed_session, title="A digital transformation program with cloud", company=None, ext="nc")
    build_business_signals(seed_session, provenance=DataProvenance.REAL, now=NOW)
    sig = seed_session.scalars(select(BusinessSignal)).first()
    assert sig.resolution_status is ResolutionStatus.REVIEW


def test_real_and_synthetic_separated(seed_session):
    _news(seed_session, title="Infosys digital transformation contract", ext="r", synthetic=False)
    _news(seed_session, title="Infosys digital transformation contract", ext="s",
          source="demo_business", synthetic=True)
    build_business_signals(seed_session, provenance=DataProvenance.REAL, now=NOW)
    build_business_signals(seed_session, provenance=DataProvenance.SYNTHETIC, now=NOW)
    real = seed_session.scalars(select(BusinessSignal).where(BusinessSignal.data_provenance == DataProvenance.REAL)).all()
    synth = seed_session.scalars(select(BusinessSignal).where(BusinessSignal.data_provenance == DataProvenance.SYNTHETIC)).all()
    assert len(real) == 1 and len(synth) == 1


# --- Job + business combination (the core competitive feature) -------------- #
def test_job_plus_business_creates_candidate(seed_session):
    for i in range(12):
        _job(seed_session, "Infosys", f"j{i}")
    _news(seed_session, title="Infosys wins digital transformation contract worth Rs 200 crore", ext="n1")
    build_job_records(seed_session, provenance=DataProvenance.REAL, now=NOW)
    result = run_business_pipeline(seed_session, provenance=DataProvenance.REAL, now=NOW)
    assert result.candidates.candidates == 1
    cand = seed_session.scalars(select(OpportunityCandidate)).first()
    assert cand.it_job_count == 12
    assert cand.total_business_signals == 1
    assert cand.status is OpportunityStatus.CANDIDATE
    assert cand.opportunity_types  # e.g. Digital Transformation Delivery
    assert cand.confidence > 0


def test_lone_partnership_is_conservative(seed_session):
    # A single non-strong signal with no hiring -> not a strong candidate.
    _news(seed_session, title="Acme partners with a cloud vendor on technology", company="Acme Corp", ext="p1")
    run_business_pipeline(seed_session, provenance=DataProvenance.REAL, now=NOW)
    cands = seed_session.scalars(select(OpportunityCandidate)).all()
    # Either no candidate, or one flagged for REVIEW (never an automatic strong lead).
    assert all(c.status is OpportunityStatus.REVIEW for c in cands)


def test_old_signal_not_recent(seed_session):
    _news(seed_session, title="Infosys digital transformation contract", ext="old", days_ago=200)
    build_business_signals(seed_session, provenance=DataProvenance.REAL, now=NOW)
    sig = seed_session.scalars(select(BusinessSignal)).first()
    assert sig.signal_age_days > 90
