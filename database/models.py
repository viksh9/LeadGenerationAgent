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
    ForeignKey,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


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


class RemoteType(str, Enum):
    ONSITE = "ONSITE"
    REMOTE = "REMOTE"
    HYBRID = "HYBRID"
    UNKNOWN = "UNKNOWN"


class JobStatus(str, Enum):
    ACTIVE = "ACTIVE"
    EXPIRED = "EXPIRED"
    UNKNOWN = "UNKNOWN"


class CollectionRunStatus(str, Enum):
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class JobRecord(Base):
    """A canonical (deduplicated) job posting.

    Many raw records / source references can map to one JobRecord — the same
    opening seen on multiple sources is ONE job here, with every source retained
    as evidence (see JobSourceReference). This is the layer the company
    aggregator counts, so a job is never double-counted across sources.
    """

    __tablename__ = "job_records"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)

    # Identity.
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    canonical_key: Mapped[str] = mapped_column(String(512), nullable=False, index=True)

    # Company.
    company_name: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    normalized_company_name: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    company_domain: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)

    # Title — the ORIGINAL source title is preserved; normalized_role is derived.
    original_job_title: Mapped[str | None] = mapped_column(String(512), nullable=True)
    normalized_role: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Location.
    original_location: Mapped[str | None] = mapped_column(String(255), nullable=True)
    country: Mapped[str | None] = mapped_column(String(64), nullable=True)
    state: Mapped[str | None] = mapped_column(String(64), nullable=True)
    city: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    remote_type: Mapped[RemoteType] = mapped_column(
        SAEnum(RemoteType, native_enum=False, length=16), default=RemoteType.UNKNOWN
    )

    # Details.
    employment_type: Mapped[str | None] = mapped_column(String(64), nullable=True)
    experience_level: Mapped[str | None] = mapped_column(String(64), nullable=True)
    salary_min: Mapped[float | None] = mapped_column(Float, nullable=True)
    salary_max: Mapped[float | None] = mapped_column(Float, nullable=True)
    currency: Mapped[str | None] = mapped_column(String(8), nullable=True)
    department: Mapped[str | None] = mapped_column(String(128), nullable=True)
    job_category: Mapped[str | None] = mapped_column(String(128), nullable=True)
    technologies: Mapped[list[str]] = mapped_column(JSON, default=list)
    skills: Mapped[list[str]] = mapped_column(JSON, default=list)

    # Dates / status.
    published_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, index=True)
    source_updated_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    job_status: Mapped[JobStatus] = mapped_column(
        SAEnum(JobStatus, native_enum=False, length=16), default=JobStatus.UNKNOWN
    )

    # Provenance / quality / evidence.
    data_provenance: Mapped[DataProvenance] = mapped_column(
        SAEnum(DataProvenance, native_enum=False, length=16), default=DataProvenance.REAL, index=True
    )
    data_quality_score: Mapped[int] = mapped_column(Integer, default=0)
    primary_source: Mapped[str | None] = mapped_column(String(64), nullable=True)
    source_count: Mapped[int] = mapped_column(Integer, default=0)
    first_seen_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    collected_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), default=utcnow)

    source_references: Mapped[list["JobSourceReference"]] = relationship(
        back_populates="job", cascade="all, delete-orphan", lazy="selectin"
    )


class JobSourceReference(Base):
    """One source that observed a canonical JobRecord.

    Retaining every source lets the evidence layer say "found on 3 sources"
    truthfully — but a reference is NOT counted as an independent opening.
    """

    __tablename__ = "job_source_references"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    job_record_id: Mapped[int] = mapped_column(ForeignKey("job_records.id", ondelete="CASCADE"), index=True)
    source_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    external_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    source_url: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    raw_record_id: Mapped[int | None] = mapped_column(Integer, nullable=True)  # soft link to raw_source_records
    source_confidence: Mapped[int] = mapped_column(Integer, default=0)
    observed_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    job: Mapped["JobRecord"] = relationship(back_populates="source_references")


class CollectionRun(Base):
    """Audit record for one collection run (per source/query)."""

    __tablename__ = "collection_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    source_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    query: Mapped[str | None] = mapped_column(String(255), nullable=True)
    location: Mapped[str | None] = mapped_column(String(128), nullable=True)
    started_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    duration_seconds: Mapped[float | None] = mapped_column(Float, nullable=True)
    pages: Mapped[int] = mapped_column(Integer, default=0)
    records_fetched: Mapped[int] = mapped_column(Integer, default=0)
    records_created: Mapped[int] = mapped_column(Integer, default=0)
    records_updated: Mapped[int] = mapped_column(Integer, default=0)
    duplicates: Mapped[int] = mapped_column(Integer, default=0)
    errors: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[CollectionRunStatus] = mapped_column(
        SAEnum(CollectionRunStatus, native_enum=False, length=16), default=CollectionRunStatus.RUNNING, index=True
    )
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)


class BusinessSignalType(str, Enum):
    """Business/market signals (distinct from Lead.signal_type so extending this
    never destabilises the existing lead signal enum / dashboard chart)."""

    PROJECT_AWARD = "PROJECT_AWARD"
    PROJECT_EXECUTION = "PROJECT_EXECUTION"
    CONTRACT = "CONTRACT"
    TENDER = "TENDER"
    DIGITAL_TRANSFORMATION = "DIGITAL_TRANSFORMATION"
    CLOUD_MIGRATION = "CLOUD_MIGRATION"
    TECHNOLOGY_MODERNIZATION = "TECHNOLOGY_MODERNIZATION"
    AI_INITIATIVE = "AI_INITIATIVE"
    PARTNERSHIP = "PARTNERSHIP"
    EXPANSION = "EXPANSION"
    DELIVERY_CENTER_EXPANSION = "DELIVERY_CENTER_EXPANSION"
    ENGINEERING_EXPANSION = "ENGINEERING_EXPANSION"
    VENDOR_REQUIREMENT = "VENDOR_REQUIREMENT"
    OUTSOURCING = "OUTSOURCING"
    ACQUISITION = "ACQUISITION"
    OTHER = "OTHER"


class SignalStrength(str, Enum):
    STRONG = "STRONG"
    MEDIUM = "MEDIUM"
    WEAK = "WEAK"


class SourceRole(str, Enum):
    PRIMARY = "PRIMARY"
    SUPPORTING = "SUPPORTING"


class ResolutionStatus(str, Enum):
    RESOLVED = "RESOLVED"
    REVIEW = "REVIEW"
    UNRESOLVED = "UNRESOLVED"


class OpportunityStatus(str, Enum):
    CANDIDATE = "CANDIDATE"
    REVIEW = "REVIEW"
    PROMOTED = "PROMOTED"      # promoted into a Lead
    REJECTED = "REJECTED"


class BusinessSignal(Base):
    """A canonical business/market signal (project, contract, tender, expansion,
    partnership, transformation, …) extracted from a real source record.

    One real-world event = ONE BusinessSignal, with every corroborating source
    kept as a SignalSourceReference. Never auto-promoted to a Lead."""

    __tablename__ = "business_signals"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)

    source_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    external_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    event_group_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)

    # Company (original preserved; normalized derived; resolution may need review).
    company_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    normalized_company_name: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    company_domain: Mapped[str | None] = mapped_column(String(255), nullable=True)
    resolution_status: Mapped[ResolutionStatus] = mapped_column(
        SAEnum(ResolutionStatus, native_enum=False, length=16), default=ResolutionStatus.UNRESOLVED
    )

    signal_type: Mapped[BusinessSignalType] = mapped_column(
        SAEnum(BusinessSignalType, native_enum=False, length=32), default=BusinessSignalType.OTHER, index=True
    )
    signal_title: Mapped[str | None] = mapped_column(String(512), nullable=True)
    signal_description: Mapped[str | None] = mapped_column(Text, nullable=True)
    signal_url: Mapped[str | None] = mapped_column(String(1024), nullable=True)

    published_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, index=True)
    updated_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    collected_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), default=utcnow)
    signal_age_days: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # Project / contract detail (only what the source explicitly states).
    project_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    project_type: Mapped[str | None] = mapped_column(String(128), nullable=True)
    project_value: Mapped[float | None] = mapped_column(Float, nullable=True)
    currency: Mapped[str | None] = mapped_column(String(8), nullable=True)
    project_value_text: Mapped[str | None] = mapped_column(String(128), nullable=True)
    contract_party: Mapped[str | None] = mapped_column(String(255), nullable=True)
    partner_name: Mapped[str | None] = mapped_column(String(255), nullable=True)

    technology_terms: Mapped[list[str]] = mapped_column(JSON, default=list)
    industry: Mapped[str | None] = mapped_column(String(128), nullable=True)
    location: Mapped[str | None] = mapped_column(String(255), nullable=True)

    signal_strength: Mapped[SignalStrength] = mapped_column(
        SAEnum(SignalStrength, native_enum=False, length=16), default=SignalStrength.WEAK, index=True
    )
    source_confidence: Mapped[int] = mapped_column(Integer, default=0)
    evidence_confidence: Mapped[int] = mapped_column(Integer, default=0)
    data_quality_score: Mapped[int] = mapped_column(Integer, default=0)

    data_provenance: Mapped[DataProvenance] = mapped_column(
        SAEnum(DataProvenance, native_enum=False, length=16), default=DataProvenance.REAL, index=True
    )
    raw_record_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    source_count: Mapped[int] = mapped_column(Integer, default=1)

    source_references: Mapped[list["SignalSourceReference"]] = relationship(
        back_populates="signal", cascade="all, delete-orphan", lazy="selectin"
    )


class SignalSourceReference(Base):
    """One source that reported a BusinessSignal (PRIMARY or SUPPORTING)."""

    __tablename__ = "signal_source_references"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    business_signal_id: Mapped[int] = mapped_column(ForeignKey("business_signals.id", ondelete="CASCADE"), index=True)
    source_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    source_url: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    external_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    published_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    observed_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    source_role: Mapped[SourceRole] = mapped_column(
        SAEnum(SourceRole, native_enum=False, length=16), default=SourceRole.PRIMARY
    )
    source_confidence: Mapped[int] = mapped_column(Integer, default=0)

    signal: Mapped["BusinessSignal"] = relationship(back_populates="source_references")


class OpportunityCandidate(Base):
    """A conservative, company-level opportunity candidate combining job
    intelligence and business signals. NOT a Lead — an intermediate stage that
    carries the inputs the Lead Scoring Engine consumes."""

    __tablename__ = "opportunity_candidates"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)

    company_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    normalized_company_name: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    company_domain: Mapped[str | None] = mapped_column(String(255), nullable=True)
    data_provenance: Mapped[DataProvenance] = mapped_column(
        SAEnum(DataProvenance, native_enum=False, length=16), default=DataProvenance.REAL, index=True
    )

    it_company_status: Mapped[str | None] = mapped_column(String(16), nullable=True)  # true|false|unknown
    it_company_confidence: Mapped[int] = mapped_column(Integer, default=0)

    # Job intelligence.
    it_job_count: Mapped[int] = mapped_column(Integer, default=0)
    recent_it_jobs: Mapped[int] = mapped_column(Integer, default=0)
    hiring_intensity: Mapped[HiringIntensity | None] = mapped_column(
        SAEnum(HiringIntensity, native_enum=False, length=16), nullable=True
    )
    top_technologies: Mapped[list[str]] = mapped_column(JSON, default=list)

    # Business intelligence.
    total_business_signals: Mapped[int] = mapped_column(Integer, default=0)
    recent_business_signals: Mapped[int] = mapped_column(Integer, default=0)
    strong_signals: Mapped[int] = mapped_column(Integer, default=0)
    project_signals: Mapped[int] = mapped_column(Integer, default=0)
    contract_signals: Mapped[int] = mapped_column(Integer, default=0)
    transformation_signals: Mapped[int] = mapped_column(Integer, default=0)
    expansion_signals: Mapped[int] = mapped_column(Integer, default=0)

    opportunity_types: Mapped[list[str]] = mapped_column(JSON, default=list)
    signal_types: Mapped[list[str]] = mapped_column(JSON, default=list)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_count: Mapped[int] = mapped_column(Integer, default=0)
    evidence_confidence: Mapped[int] = mapped_column(Integer, default=0)
    confidence: Mapped[int] = mapped_column(Integer, default=0)
    last_signal_date: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    status: Mapped[OpportunityStatus] = mapped_column(
        SAEnum(OpportunityStatus, native_enum=False, length=16), default=OpportunityStatus.CANDIDATE, index=True
    )
    lead_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), default=utcnow)
