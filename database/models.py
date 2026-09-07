"""SQLAlchemy 2.x models for the Lead store (Phase 1).

A `Lead` is a single denormalized row capturing a company, the intent signal
that surfaced it, enrichment/contact details, and the scoring/outreach fields
that later phases will populate. Signal detection, enrichment, and outreach are
NOT implemented here — the columns simply hold whatever those phases produce.
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum

from sqlalchemy import (
    JSON,
    CheckConstraint,
    DateTime,
    Enum as SAEnum,
    Float,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def utcnow() -> datetime:
    """Naive UTC timestamp (SQLite stores no tzinfo)."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


class Base(DeclarativeBase):
    pass


class SignalType(str, Enum):
    HIRING = "HIRING"
    PROJECT_AWARD = "PROJECT_AWARD"
    PROJECT_EXECUTION = "PROJECT_EXECUTION"
    EXPANSION = "EXPANSION"
    DIGITAL_TRANSFORMATION = "DIGITAL_TRANSFORMATION"
    TECHNOLOGY_INITIATIVE = "TECHNOLOGY_INITIATIVE"
    VENDOR_REQUIREMENT = "VENDOR_REQUIREMENT"
    CONTRACT = "CONTRACT"
    OTHER = "OTHER"


class LeadPriority(str, Enum):
    HOT = "HOT"
    WARM = "WARM"
    NURTURE = "NURTURE"
    LOW = "LOW"


class LeadStatus(str, Enum):
    NEW = "NEW"
    RESEARCHED = "RESEARCHED"
    CONTACTED = "CONTACTED"
    REPLIED = "REPLIED"
    MEETING = "MEETING"
    QUALIFIED = "QUALIFIED"
    PROPOSAL = "PROPOSAL"
    WON = "WON"
    LOST = "LOST"
    NURTURE = "NURTURE"


class DataProvenance(str, Enum):
    """Whether a lead was built from real collected data or synthetic/demo data.

    The production dashboard shows REAL only; SYNTHETIC is for development/demo
    and must always be visibly labelled.
    """

    REAL = "REAL"
    SYNTHETIC = "SYNTHETIC"


class HiringIntensity(str, Enum):
    """Company-level hiring intensity derived from aggregated IT job activity."""

    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    VERY_HIGH = "VERY_HIGH"


class CompanyType(str, Enum):
    """Best-effort classification of a technology company (evidence-based)."""

    IT_SERVICES = "IT_SERVICES"
    SOFTWARE_PRODUCT = "SOFTWARE_PRODUCT"
    SAAS = "SAAS"
    CLOUD = "CLOUD"
    AI_ML = "AI_ML"
    CYBERSECURITY = "CYBERSECURITY"
    FINTECH_TECH = "FINTECH_TECH"
    HEALTHTECH = "HEALTHTECH"
    ECOMMERCE_TECH = "ECOMMERCE_TECH"
    ENTERPRISE_SOFTWARE = "ENTERPRISE_SOFTWARE"
    IT_CONSULTING = "IT_CONSULTING"
    DIGITAL_TRANSFORMATION = "DIGITAL_TRANSFORMATION"
    OTHER_TECHNOLOGY = "OTHER_TECHNOLOGY"


class Lead(Base):
    """Denormalized prospect row used across scoring, enrichment, and outreach."""

    __tablename__ = "leads"

    # Constraints are intentionally permissive: everything except company_name is
    # optional so future data sources can insert partial records, and the numeric
    # bounds only apply when a value is actually supplied.
    __table_args__ = (
        CheckConstraint(
            "lead_score IS NULL OR (lead_score >= 0 AND lead_score <= 100)",
            name="ck_leads_lead_score_range",
        ),
        CheckConstraint(
            "signal_confidence IS NULL OR (signal_confidence >= 0 AND signal_confidence <= 100)",
            name="ck_leads_signal_confidence_range",
        ),
        CheckConstraint(
            "estimated_hiring IS NULL OR estimated_hiring >= 0",
            name="ck_leads_estimated_hiring_nonneg",
        ),
        CheckConstraint(
            "project_value IS NULL OR project_value >= 0",
            name="ck_leads_project_value_nonneg",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)

    # Company
    company_name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    normalized_company_name: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    company_domain: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    company_type: Mapped[CompanyType | None] = mapped_column(
        SAEnum(CompanyType, native_enum=False, length=32), nullable=True
    )
    industry: Mapped[str | None] = mapped_column(String(128), nullable=True)
    location: Mapped[str | None] = mapped_column(String(255), nullable=True)
    company_size: Mapped[str | None] = mapped_column(String(64), nullable=True)
    company_website: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # Company-level hiring aggregation (one lead == one company opportunity).
    it_job_count: Mapped[int] = mapped_column(Integer, default=0)
    recent_job_count: Mapped[int] = mapped_column(Integer, default=0)
    hiring_intensity: Mapped[HiringIntensity | None] = mapped_column(
        SAEnum(HiringIntensity, native_enum=False, length=16), nullable=True, index=True
    )
    primary_target_role: Mapped[str | None] = mapped_column(String(128), nullable=True)
    company_signals: Mapped[list[str]] = mapped_column(JSON, default=list)

    # Signal
    signal_type: Mapped[SignalType | None] = mapped_column(
        SAEnum(SignalType, native_enum=False, length=32), nullable=True, index=True
    )
    signal_title: Mapped[str | None] = mapped_column(String(512), nullable=True)
    signal_description: Mapped[str | None] = mapped_column(Text, nullable=True)
    signal_date: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    source_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    source_url: Mapped[str | None] = mapped_column(String(1024), nullable=True)

    # Opportunity detail
    technologies: Mapped[list[str]] = mapped_column(JSON, default=list)
    project_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    project_value: Mapped[float | None] = mapped_column(Float, nullable=True)
    estimated_hiring: Mapped[int | None] = mapped_column(Integer, nullable=True)
    hiring_roles: Mapped[list[str]] = mapped_column(JSON, default=list)

    # Point of contact
    poc_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    poc_title: Mapped[str | None] = mapped_column(String(255), nullable=True)
    poc_linkedin_url: Mapped[str | None] = mapped_column(String(512), nullable=True)
    public_contact: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # Scoring / prioritization
    signal_confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    lead_score: Mapped[float] = mapped_column(Float, default=0.0, index=True)
    lead_priority: Mapped[LeadPriority] = mapped_column(
        SAEnum(LeadPriority, native_enum=False, length=16),
        default=LeadPriority.LOW,
        index=True,
    )

    # Outreach guidance
    opportunity_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    recommended_action: Mapped[str | None] = mapped_column(String(255), nullable=True)
    recommended_pitch: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Evidence / provenance (every lead must be explainable).
    data_provenance: Mapped[DataProvenance] = mapped_column(
        SAEnum(DataProvenance, native_enum=False, length=16),
        default=DataProvenance.REAL,
        index=True,
    )
    source_count: Mapped[int] = mapped_column(Integer, default=0)
    # evidence: list of {source, source_id, source_url, job_title, published_at,
    # external_id} — the job postings that support this company opportunity.
    evidence: Mapped[list[dict]] = mapped_column(JSON, default=list)
    last_signal_date: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    # Lifecycle
    status: Mapped[LeadStatus] = mapped_column(
        SAEnum(LeadStatus, native_enum=False, length=16),
        default=LeadStatus.NEW,
        index=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), default=utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), default=utcnow, onupdate=utcnow
    )
    last_verified_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class RecordType(str, Enum):
    """Kind of raw record collected from a source."""

    JOB_POSTING = "JOB_POSTING"
    COMPANY_PROFILE = "COMPANY_PROFILE"
    NEWS_ARTICLE = "NEWS_ARTICLE"
    PROJECT = "PROJECT"
    TENDER = "TENDER"
    OTHER = "OTHER"


class RawStatus(str, Enum):
    """Lifecycle of a raw record within the internal ingestion pipeline."""

    NEW = "NEW"
    NORMALIZED = "NORMALIZED"
    PROCESSED = "PROCESSED"
    DUPLICATE = "DUPLICATE"
    INVALID = "INVALID"


class RawSourceRecord(Base):
    """Immutable-ish raw record collected from an external source.

    This is the INTERNAL ingestion layer — kept logically separate from the
    derived `Lead`. Normalization/dedup/scoring read from here; they do not run
    inside this model. `raw_payload` stores the original source JSON as data only.
    """

    __tablename__ = "raw_source_records"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)

    # Provenance / identity.
    source_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    external_id: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    source_url: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False, index=True)

    # Freshness timestamps.
    collected_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), default=utcnow, index=True
    )
    published_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, index=True)
    updated_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    # Content.
    record_type: Mapped[RecordType] = mapped_column(
        SAEnum(RecordType, native_enum=False, length=32), default=RecordType.OTHER
    )
    title: Mapped[str | None] = mapped_column(String(512), nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Company identity foundation.
    company_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    normalized_company_name: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    company_domain: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    source_company_id: Mapped[str | None] = mapped_column(String(255), nullable=True)

    location: Mapped[str | None] = mapped_column(String(255), nullable=True)
    industry: Mapped[str | None] = mapped_column(String(128), nullable=True)
    technologies: Mapped[list[str]] = mapped_column(JSON, default=list)
    roles: Mapped[list[str]] = mapped_column(JSON, default=list)
    salary: Mapped[str | None] = mapped_column(String(128), nullable=True)
    project_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    project_value: Mapped[float | None] = mapped_column(Float, nullable=True)
    contract_type: Mapped[str | None] = mapped_column(String(128), nullable=True)

    # Original payload (data only) + flags.
    raw_payload: Mapped[dict] = mapped_column(JSON, default=dict)
    is_synthetic: Mapped[bool] = mapped_column(default=False, index=True)
    raw_status: Mapped[RawStatus] = mapped_column(
        SAEnum(RawStatus, native_enum=False, length=16), default=RawStatus.NEW, index=True
    )
    # Set once a raw record has been normalized into a Lead (soft link, no FK
    # constraint so raw records survive lead deletion for provenance).
    lead_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
