"""Tests for the real-data ingestion foundation (registry, collectors, raw model).

All synthetic; no external network calls.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from collectors.base import (
    BaseCollector,
    CollectorResult,
    FetchRequest,
    HealthCheckResult,
    HealthStatus,
    RateLimiter,
    RetryConfig,
    TimeoutConfig,
)
from collectors.raw_record import RawRecordDraft, compute_content_hash, normalize_company_name
from collectors.source_registry import (
    ComplianceStatus,
    SourceCategory,
    SourceDefinition,
    SourceRegistry,
    SourceStatus,
    SourceType,
    get_registry,
    load_sources,
    source_api_key,
)
from config.industries import IT_SEGMENTS, PRIMARY_INDUSTRY, is_it_segment
from config.target_signals import TARGET_SIGNALS, signal_type_for
from database.models import RawSourceRecord, SignalType
from database.raw_repository import (
    create_raw_record_from_draft,
    find_by_content_hash,
    find_by_external_id,
    get_raw_record,
    list_raw_records,
)

NOW = datetime(2026, 9, 7, tzinfo=timezone.utc)


def _draft(**overrides) -> RawRecordDraft:
    base = dict(
        source_id="adzuna",
        external_id="job-123",
        source_url="https://synthetic.example/jobs/123",
        title="Hiring 20 Java Engineers",
        company_name="ABC Technologies Pvt Ltd",
        record_type="JOB_POSTING",
        published_at=NOW,
        technologies=["Java", "AWS"],
        roles=["Java Engineer"],
        is_synthetic=True,
    )
    base.update(overrides)
    return RawRecordDraft(**base)


# 1-6: config -----------------------------------------------------------------
def test_source_definition_validation():
    src = SourceDefinition(
        source_id="x", name="X", category=SourceCategory.JOB, source_type=SourceType.API
    )
    assert src.status == SourceStatus.PLANNED
    assert src.enabled is False
    with pytest.raises(ValidationError):
        SourceDefinition(source_id="y", name="Y", category="NOPE", source_type=SourceType.API)


def test_source_registry_loads_no_source_is_connected():
    registry = get_registry()
    assert len(registry) >= 5
    # Nothing is CONNECTED (no live-verified source); Adzuna is AVAILABLE (built).
    assert all(s.status != SourceStatus.CONNECTED for s in registry.all())
    assert registry.get("adzuna").status == SourceStatus.AVAILABLE
    assert registry.get("does-not-exist") is None


def test_source_registry_filters():
    registry = get_registry()
    jobs = registry.list(category=SourceCategory.JOB)
    assert all(s.category == SourceCategory.JOB for s in jobs)
    planned = registry.list(status=SourceStatus.PLANNED)
    assert 0 < len(planned) < len(registry)  # most planned, Adzuna available


def test_registry_rejects_duplicate_ids():
    a = SourceDefinition(source_id="dup", name="A", category=SourceCategory.JOB, source_type=SourceType.API)
    b = SourceDefinition(source_id="dup", name="B", category=SourceCategory.NEWS, source_type=SourceType.RSS)
    with pytest.raises(ValueError):
        SourceRegistry([a, b])


def test_compliance_status_present():
    src = get_registry().get("company_career_pages")
    assert src is not None
    assert isinstance(src.compliance.robots_status, ComplianceStatus)


def test_it_industry_configuration():
    assert PRIMARY_INDUSTRY == "IT"
    assert "SaaS" in IT_SEGMENTS
    assert is_it_segment("saas")
    assert not is_it_segment("Agriculture")


def test_target_signals_map_to_signal_type():
    assert signal_type_for("CLOUD_MIGRATION") == SignalType.DIGITAL_TRANSFORMATION
    assert signal_type_for("STAFF_AUGMENTATION") == SignalType.VENDOR_REQUIREMENT
    assert signal_type_for("unknown") is None
    assert all(isinstance(t.signal_type, SignalType) for t in TARGET_SIGNALS)


# 7-8: collector interface ----------------------------------------------------
def test_base_collector_is_abstract():
    src = get_registry().get("adzuna")
    with pytest.raises(TypeError):
        BaseCollector(src)  # abstract fetch()


def test_collector_result_and_metadata():
    result = CollectorResult(source_id="adzuna", records=[_draft()], has_more=True, next_cursor="c2")
    assert result.records_count == 1
    assert result.has_more is True
    assert result.errors == [] and result.warnings == []


def test_fetch_request_incremental_capability():
    req = FetchRequest(since=NOW, cursor="abc", after_external_id="job-1", page=2, limit=50)
    assert req.since == NOW and req.cursor == "abc"


# 9-13: raw record ------------------------------------------------------------
def test_raw_record_draft_derives_hash_and_normalized_name():
    d = _draft()
    assert d.content_hash and len(d.content_hash) == 64
    assert d.normalized_company_name == "abc technologies"


def test_company_normalization_matches_variants():
    assert normalize_company_name("ABC Technologies Pvt Ltd") == normalize_company_name("ABC Technologies")
    assert normalize_company_name("Foo Bar, Inc.") == "foo bar"


def test_content_hash_deterministic_and_ignores_time():
    kw = dict(source_id="s", external_id="e", source_url="u", title="t", company_name="Co Ltd")
    h1 = compute_content_hash(published_at=datetime(2026, 9, 7, 9, 0, tzinfo=timezone.utc), **kw)
    h2 = compute_content_hash(published_at=datetime(2026, 9, 7, 23, 0, tzinfo=timezone.utc), **kw)
    assert h1 == h2  # same day -> same hash
    h3 = compute_content_hash(published_at=datetime(2026, 9, 8, tzinfo=timezone.utc), **kw)
    assert h3 != h1


def test_freshness_and_synthetic_flag_fields():
    d = _draft(is_synthetic=False, updated_at=NOW)
    assert d.is_synthetic is False
    assert d.published_at == NOW and d.updated_at == NOW


# 14-17: network policy -------------------------------------------------------
def test_rate_limiter_enforces_window():
    ticks = iter([0.0, 0.0, 0.0, 61.0])
    limiter = RateLimiter(2, clock=lambda: next(ticks))
    assert limiter.allow() is True   # t=0
    assert limiter.allow() is True   # t=0
    assert limiter.allow() is False  # t=0, over limit
    assert limiter.allow() is True   # t=61, window rolled


def test_retry_config_never_retries_client_errors():
    retry = RetryConfig()
    assert retry.is_retryable(503) is True
    assert retry.is_retryable(429) is True
    assert retry.is_retryable(401) is False
    assert retry.is_retryable(404) is False
    assert retry.backoff_for(1) <= retry.backoff_for(2) <= retry.backoff_max_seconds


def test_timeout_config_defaults():
    t = TimeoutConfig()
    assert t.connect_timeout > 0 and t.read_timeout > 0


def test_health_check_reports_status():
    class _Stub(BaseCollector):
        def fetch(self, request=None):
            return CollectorResult(source_id=self.source_id)

    src = get_registry().get("adzuna")
    health = _Stub(src).health_check()
    assert isinstance(health, HealthCheckResult)
    # adzuna requires an API key that isn't set in tests -> NOT_CONFIGURED
    assert health.status == HealthStatus.NOT_CONFIGURED


# 18-19: security -------------------------------------------------------------
def test_source_definition_serialization_has_no_secret(monkeypatch):
    monkeypatch.setenv("SOURCE_ADZUNA_API_KEY", "super-secret-value")
    src = get_registry().get("adzuna")
    dumped = src.model_dump_json()
    assert "super-secret-value" not in dumped  # key lives only in the environment
    assert source_api_key("adzuna") == "super-secret-value"


def test_no_secret_in_logs(monkeypatch, caplog):
    monkeypatch.setenv("SOURCE_ADZUNA_API_KEY", "leak-me-not")

    class _Stub(BaseCollector):
        def fetch(self, request=None):
            return CollectorResult(source_id=self.source_id)

    src = get_registry().get("adzuna")
    with caplog.at_level(logging.INFO, logger="collectors"):
        _Stub(src).fetch_incremental(FetchRequest())
    assert "leak-me-not" not in caplog.text


# 20 + 22/26: repository + raw payload ---------------------------------------
def test_repository_roundtrip_and_lookups(db_session):
    draft = _draft()
    rec = create_raw_record_from_draft(db_session, draft)
    assert rec.id is not None
    assert get_raw_record(db_session, rec.id).content_hash == draft.content_hash
    assert find_by_external_id(db_session, "adzuna", "job-123").id == rec.id
    assert find_by_content_hash(db_session, draft.content_hash).id == rec.id
    assert len(list_raw_records(db_session, source_id="adzuna")) == 1


def test_duplicate_external_id_detectable(db_session):
    create_raw_record_from_draft(db_session, _draft())
    # A second collection of the same external id is discoverable before insert.
    existing = find_by_external_id(db_session, "adzuna", "job-123")
    assert existing is not None


def test_raw_payload_is_data_not_executed(db_session):
    payload = {"cmd": "__import__('os').system('echo hi')", "nested": {"a": 1}}
    rec = create_raw_record_from_draft(db_session, _draft(raw_payload=payload))
    stored = get_raw_record(db_session, rec.id)
    assert stored.raw_payload == payload  # stored verbatim as data, never evaluated


def test_sources_yaml_valid():
    sources = load_sources()
    assert sources
    assert all(s.enabled is False for s in sources)  # nothing enabled/connected yet
