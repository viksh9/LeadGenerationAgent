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
    UniqueConstraint,
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
    CONSULTING = "CONSULTING"
    SYSTEM_INTEGRATOR = "SYSTEM_INTEGRATOR"
    OUTSOURCING = "OUTSOURCING"
    STAFFING_TECH = "STAFFING_TECH"
    OTHER_TECHNOLOGY = "OTHER_TECHNOLOGY"


class CompanyMatchStatus(str, Enum):
    EXACT_MATCH = "EXACT_MATCH"
    HIGH_CONFIDENCE_MATCH = "HIGH_CONFIDENCE_MATCH"
    POSSIBLE_MATCH = "POSSIBLE_MATCH"
    REVIEW_REQUIRED = "REVIEW_REQUIRED"
    NO_MATCH = "NO_MATCH"
    CONFLICT = "CONFLICT"


class CompanyRelationshipType(str, Enum):
    PARENT_OF = "PARENT_OF"
    SUBSIDIARY_OF = "SUBSIDIARY_OF"
    BRAND_OF = "BRAND_OF"
    DIVISION_OF = "DIVISION_OF"
    ACQUIRED_BY = "ACQUIRED_BY"
    MERGED_WITH = "MERGED_WITH"
    RELATED_TO = "RELATED_TO"


class CompanyResolutionDecision(str, Enum):
    PENDING = "PENDING"
    MERGE = "MERGE"
    KEEP_SEPARATE = "KEEP_SEPARATE"
    IGNORE = "IGNORE"


class HiringTrend(str, Enum):
    RAPIDLY_INCREASING = "RAPIDLY_INCREASING"
    INCREASING = "INCREASING"
    STABLE = "STABLE"
    DECREASING = "DECREASING"
    LOW_ACTIVITY = "LOW_ACTIVITY"
    UNKNOWN = "UNKNOWN"


class DemandStrength(str, Enum):
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"


class VerificationStatus(str, Enum):
    """How strongly the evidence supports the claim (separate from lead score)."""

    VERIFIED = "VERIFIED"
    PARTIALLY_VERIFIED = "PARTIALLY_VERIFIED"
    UNVERIFIED = "UNVERIFIED"
    CONTRADICTED = "CONTRADICTED"
    STALE = "STALE"


class LeadReadiness(str, Enum):
    """Whether a lead is ready for sales action, based on EVIDENCE quality."""

    READY = "READY"
    REVIEW_REQUIRED = "REVIEW_REQUIRED"
    HOLD = "HOLD"
    DISCARD = "DISCARD"


class SourceTier(str, Enum):
    TIER_1 = "TIER_1"   # official (career page, company site, government, tender portal)
    TIER_2 = "TIER_2"   # official ATS / licensed provider / reputable publication
    TIER_3 = "TIER_3"   # secondary aggregator / syndication / unknown third-party
    TIER_4 = "TIER_4"   # unknown / untrusted


class EvidenceType(str, Enum):
    JOB = "JOB"
    BUSINESS_SIGNAL = "BUSINESS_SIGNAL"
    NEWS = "NEWS"
    PROJECT = "PROJECT"
    TENDER = "TENDER"
    COMPANY = "COMPANY"
    OTHER = "OTHER"


class ConflictType(str, Enum):
    JOB_STATUS = "JOB_STATUS"
    PROJECT_STATUS = "PROJECT_STATUS"
    TENDER_STATUS = "TENDER_STATUS"
    COMPANY_IDENTITY = "COMPANY_IDENTITY"
    LOCATION = "LOCATION"
    JOB_TITLE = "JOB_TITLE"
    DATE = "DATE"
    STAFFING_ESTIMATE = "STAFFING_ESTIMATE"
    OTHER = "OTHER"


class ConflictSeverity(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"


class EvidenceResolutionStatus(str, Enum):
    UNRESOLVED = "UNRESOLVED"
    RESOLVED = "RESOLVED"
    IGNORED = "IGNORED"


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
    company_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)  # -> Company (soft link)
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

    # Verification intelligence — kept STRICTLY SEPARATE from lead_score. A lead
    # can be commercially HOT yet only PARTIALLY_VERIFIED (or vice versa).
    source_reliability: Mapped[int] = mapped_column(Integer, default=0)
    evidence_confidence: Mapped[int] = mapped_column(Integer, default=0)
    freshness_score: Mapped[int] = mapped_column(Integer, default=0)
    independent_support_count: Mapped[int] = mapped_column(Integer, default=0)
    verification_status: Mapped[VerificationStatus] = mapped_column(
        SAEnum(VerificationStatus, native_enum=False, length=24),
        default=VerificationStatus.UNVERIFIED, index=True,
    )
    lead_readiness: Mapped[LeadReadiness] = mapped_column(
        SAEnum(LeadReadiness, native_enum=False, length=16),
        default=LeadReadiness.REVIEW_REQUIRED, index=True,
    )
    verification_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    verification_version: Mapped[str | None] = mapped_column(String(16), nullable=True)
    verified_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

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


class SourceConnectionStatus(str, Enum):
    """Truthful, persisted connectivity state of a real external source.

    CONNECTED is only ever set after a real request actually succeeded. A
    collector existing (implemented) is not the same as CONNECTED.
    """

    NOT_CONFIGURED = "NOT_CONFIGURED"                  # credentials/config absent
    CONFIGURED = "CONFIGURED"                          # credentials present, unverified
    CONNECTED = "CONNECTED"                            # a real request succeeded
    AUTHENTICATION_FAILED = "AUTHENTICATION_FAILED"    # credentials rejected (401/403)
    RATE_LIMITED = "RATE_LIMITED"                      # throttled (429)
    TEMPORARILY_UNAVAILABLE = "TEMPORARILY_UNAVAILABLE"  # 5xx / network / timeout
    DISABLED = "DISABLED"
    ERROR = "ERROR"


class AtsProvider(str, Enum):
    """Applicant Tracking System / official career-source provider."""

    GREENHOUSE = "GREENHOUSE"
    LEVER = "LEVER"
    CAREER_PAGE = "CAREER_PAGE"     # generic official career page (non-ATS)
    OTHER = "OTHER"


class CareerSourceStatus(str, Enum):
    """State of a discovered company career/ATS source.

    DISCOVERY_REQUIRED means we know the company but not (yet) a legitimate board
    identifier / endpoint to collect from — never a fabricated board.
    """

    DISCOVERY_REQUIRED = "DISCOVERY_REQUIRED"
    CONFIGURED = "CONFIGURED"       # board identifier known, not yet verified
    CONNECTED = "CONNECTED"         # a real public request succeeded
    DISABLED = "DISABLED"
    ERROR = "ERROR"


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

    # Cross-source deduplication (processors/deduplication). Normalized title kept
    # for matching; original titles from EVERY source retained; per-field source
    # conflicts recorded rather than silently overwritten.
    normalized_title: Mapped[str | None] = mapped_column(String(512), nullable=True, index=True)
    original_job_titles: Mapped[list[str]] = mapped_column(JSON, default=list)
    field_conflicts: Mapped[dict] = mapped_column(JSON, default=dict)
    deduplication_version: Mapped[str | None] = mapped_column(String(16), nullable=True)

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
    source_priority: Mapped[int | None] = mapped_column(Integer, nullable=True)
    is_primary_source: Mapped[bool] = mapped_column(default=False)
    published_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    observed_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), default=utcnow)

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


class SourceHealth(Base):
    """Persisted connectivity health of a real external source (one row per source).

    Updated by the connectivity service after a real check. Stores the last check
    outcome and timestamps so the UI/API can report truthful status and history.
    Never stores credentials; last_error is a safe, credential-free message.
    """

    __tablename__ = "source_health"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    source_id: Mapped[str] = mapped_column(String(64), nullable=False, unique=True, index=True)
    connection_status: Mapped[SourceConnectionStatus] = mapped_column(
        SAEnum(SourceConnectionStatus, native_enum=False, length=32),
        default=SourceConnectionStatus.NOT_CONFIGURED,
        index=True,
    )
    last_checked_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    last_success_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    last_failure_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    last_error: Mapped[str | None] = mapped_column(String(512), nullable=True)
    checks_total: Mapped[int] = mapped_column(Integer, default=0)
    checks_ok: Mapped[int] = mapped_column(Integer, default=0)
    # Persistent request-budget tracking (e.g. Jooble's 500-request LIFETIME free
    # cap). request_budget is None when the source has no fixed lifetime budget.
    requests_used: Mapped[int] = mapped_column(Integer, default=0)
    request_budget: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)


class CompanyCareerSource(Base):
    """A discovered official company career / ATS source (Greenhouse, Lever, …).

    Persists a legitimately-identified board so a company-specific collector can be
    activated. Never holds a fabricated board — until a real board identifier is
    known the status is DISCOVERY_REQUIRED. Mirrors the CompanySourceReference
    pattern; company_id is optional (the company may not be resolved yet).
    """

    __tablename__ = "company_career_sources"
    __table_args__ = (
        UniqueConstraint("ats_provider", "board_identifier", name="uq_career_source_provider_board"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    company_id: Mapped[int | None] = mapped_column(
        ForeignKey("companies.id", ondelete="SET NULL"), nullable=True, index=True
    )
    company_name: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    ats_provider: Mapped[AtsProvider] = mapped_column(
        SAEnum(AtsProvider, native_enum=False, length=16), index=True
    )
    board_identifier: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    careers_url: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    discovery_method: Mapped[str | None] = mapped_column(String(64), nullable=True)
    status: Mapped[CareerSourceStatus] = mapped_column(
        SAEnum(CareerSourceStatus, native_enum=False, length=24),
        default=CareerSourceStatus.DISCOVERY_REQUIRED,
        index=True,
    )
    enabled: Mapped[bool] = mapped_column(default=False, index=True)
    last_checked_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    last_success_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    last_error: Mapped[str | None] = mapped_column(String(512), nullable=True)
    data_provenance: Mapped[DataProvenance] = mapped_column(
        SAEnum(DataProvenance, native_enum=False, length=16), default=DataProvenance.REAL
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)


class BusinessSignalType(str, Enum):
    """Business/market signals (distinct from Lead.signal_type so extending this
    never destabilises the existing lead signal enum / dashboard chart)."""

    PROJECT_AWARD = "PROJECT_AWARD"
    PROJECT_EXECUTION = "PROJECT_EXECUTION"
    CONTRACT = "CONTRACT"
    TENDER = "TENDER"
    GOVERNMENT_TENDER = "GOVERNMENT_TENDER"
    RFP = "RFP"
    IT_CONTRACT = "IT_CONTRACT"
    DIGITAL_TRANSFORMATION = "DIGITAL_TRANSFORMATION"
    CLOUD_MIGRATION = "CLOUD_MIGRATION"
    TECHNOLOGY_MODERNIZATION = "TECHNOLOGY_MODERNIZATION"
    TECHNOLOGY_INITIATIVE = "TECHNOLOGY_INITIATIVE"
    AI_INITIATIVE = "AI_INITIATIVE"
    CYBERSECURITY_INITIATIVE = "CYBERSECURITY_INITIATIVE"
    SYSTEM_IMPLEMENTATION = "SYSTEM_IMPLEMENTATION"
    PARTNERSHIP = "PARTNERSHIP"
    EXPANSION = "EXPANSION"
    TECH_CENTER_EXPANSION = "TECH_CENTER_EXPANSION"
    OFFICE_EXPANSION = "OFFICE_EXPANSION"
    DELIVERY_CENTER_EXPANSION = "DELIVERY_CENTER_EXPANSION"
    ENGINEERING_EXPANSION = "ENGINEERING_EXPANSION"
    VENDOR_REQUIREMENT = "VENDOR_REQUIREMENT"
    OUTSOURCING = "OUTSOURCING"
    ACQUISITION = "ACQUISITION"
    OTHER = "OTHER"


class TenderStatus(str, Enum):
    """Lifecycle status of a government/procurement tender (from source data only)."""

    OPEN = "OPEN"
    CLOSING_SOON = "CLOSING_SOON"
    CLOSED = "CLOSED"
    CANCELLED = "CANCELLED"
    AWARDED = "AWARDED"
    UNKNOWN = "UNKNOWN"


class CommercialIntent(str, Enum):
    """Deterministic commercial-intent classification (kept separate from evidence
    confidence and lead score)."""

    VERY_HIGH = "VERY_HIGH"
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"
    UNKNOWN = "UNKNOWN"


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
    # Resolved canonical company (nullable; resolution may be pending/review).
    company_id: Mapped[int | None] = mapped_column(
        ForeignKey("companies.id", ondelete="SET NULL"), nullable=True, index=True
    )
    # Deterministic commercial-intent (separate from evidence/source confidence).
    commercial_intent: Mapped[CommercialIntent] = mapped_column(
        SAEnum(CommercialIntent, native_enum=False, length=16), default=CommercialIntent.UNKNOWN
    )

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


class TenderRecord(Base):
    """A government/procurement tender or RFP from a permitted real source.

    Only what the source explicitly states is stored; absent values stay NULL (never
    fabricated). The issuing organization (signal_origin_organization) is kept
    separate from any named awarded vendor/target company (§15). One canonical
    tender per (source_id, source_record_id); history is preserved (not deleted)."""

    __tablename__ = "tender_records"
    __table_args__ = (
        UniqueConstraint("source_id", "source_record_id", name="uq_tender_source_record"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    source_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    source_record_id: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False, index=True)

    title: Mapped[str | None] = mapped_column(String(512), nullable=True)
    # Issuing organization (the buyer) — NOT necessarily the commercial target.
    organization_name: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    department: Mapped[str | None] = mapped_column(String(255), nullable=True)
    organization_type: Mapped[str | None] = mapped_column(String(64), nullable=True)  # GOVERNMENT/PSU/PRIVATE/UNKNOWN
    location: Mapped[str | None] = mapped_column(String(255), nullable=True)

    issue_date: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    publication_date: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, index=True)
    closing_date: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, index=True)
    award_date: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    estimated_value: Mapped[float | None] = mapped_column(Float, nullable=True)   # NULL if source omits
    currency: Mapped[str | None] = mapped_column(String(8), nullable=True)
    estimated_value_text: Mapped[str | None] = mapped_column(String(128), nullable=True)

    category: Mapped[str | None] = mapped_column(String(128), nullable=True)
    technologies: Mapped[list[str]] = mapped_column(JSON, default=list)
    scope_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    eligibility_summary: Mapped[str | None] = mapped_column(Text, nullable=True)

    tender_status: Mapped[TenderStatus] = mapped_column(
        SAEnum(TenderStatus, native_enum=False, length=16), default=TenderStatus.UNKNOWN, index=True
    )
    source_url: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    raw_record_id: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # §15: issuer org vs any named awarded/target vendor company.
    signal_origin_organization: Mapped[str | None] = mapped_column(String(255), nullable=True)
    company_id: Mapped[int | None] = mapped_column(
        ForeignKey("companies.id", ondelete="SET NULL"), nullable=True, index=True
    )
    target_company_id: Mapped[int | None] = mapped_column(
        ForeignKey("companies.id", ondelete="SET NULL"), nullable=True, index=True
    )
    business_signal_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)

    evidence_confidence: Mapped[int] = mapped_column(Integer, default=0)
    freshness_score: Mapped[int] = mapped_column(Integer, default=0)
    commercial_intent: Mapped[CommercialIntent] = mapped_column(
        SAEnum(CommercialIntent, native_enum=False, length=16), default=CommercialIntent.UNKNOWN
    )
    data_provenance: Mapped[DataProvenance] = mapped_column(
        SAEnum(DataProvenance, native_enum=False, length=16), default=DataProvenance.REAL, index=True
    )
    first_seen_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)


class MatchConfidence(str, Enum):
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"
    NO_MATCH = "NO_MATCH"


class MatchDecision(str, Enum):
    AUTO_MERGE = "AUTO_MERGE"
    REVIEW = "REVIEW"
    NO_MATCH = "NO_MATCH"


class DuplicateStatus(str, Enum):
    PENDING = "PENDING"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"


class JobDuplicateCandidate(Base):
    """A MEDIUM-confidence potential duplicate held for human review — never
    auto-merged. Keeps the explanation (matched fields + differences)."""

    __tablename__ = "job_duplicate_candidates"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    canonical_job_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    record_a: Mapped[dict] = mapped_column(JSON, default=dict)   # {source_id, external_id, title, ...}
    record_b: Mapped[dict] = mapped_column(JSON, default=dict)
    match_score: Mapped[int] = mapped_column(Integer, default=0)
    match_confidence: Mapped[MatchConfidence] = mapped_column(
        SAEnum(MatchConfidence, native_enum=False, length=16), default=MatchConfidence.LOW
    )
    matched_fields: Mapped[list[str]] = mapped_column(JSON, default=list)
    differences: Mapped[list[str]] = mapped_column(JSON, default=list)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    data_provenance: Mapped[DataProvenance] = mapped_column(
        SAEnum(DataProvenance, native_enum=False, length=16), default=DataProvenance.REAL, index=True
    )
    status: Mapped[DuplicateStatus] = mapped_column(
        SAEnum(DuplicateStatus, native_enum=False, length=16), default=DuplicateStatus.PENDING, index=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), default=utcnow)


class EvidenceRecord(Base):
    """First-class evidence supporting a job / signal / lead / company.

    References existing RawSourceRecord data (no large raw payloads duplicated).
    Carries FOUR distinct scores kept separate: source_reliability, authority,
    freshness, and evidence_confidence. Verification is versioned + re-runnable.
    """

    __tablename__ = "evidence_records"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    raw_source_record_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    canonical_job_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    business_signal_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    lead_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    company_normalized_name: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)

    evidence_type: Mapped[EvidenceType] = mapped_column(
        SAEnum(EvidenceType, native_enum=False, length=24), default=EvidenceType.OTHER, index=True
    )
    source_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    source_category: Mapped[str | None] = mapped_column(String(64), nullable=True)
    source_url: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    source_domain: Mapped[str | None] = mapped_column(String(255), nullable=True)
    source_tier: Mapped[SourceTier] = mapped_column(
        SAEnum(SourceTier, native_enum=False, length=16), default=SourceTier.TIER_4, index=True
    )

    observed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    published_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    last_verified_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False, index=True)

    evidence_title: Mapped[str | None] = mapped_column(String(512), nullable=True)
    evidence_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    extracted_claims: Mapped[list[str]] = mapped_column(JSON, default=list)

    data_provenance: Mapped[DataProvenance] = mapped_column(
        SAEnum(DataProvenance, native_enum=False, length=16), default=DataProvenance.REAL, index=True
    )
    # FOUR distinct scores — never collapsed into one.
    source_reliability_score: Mapped[int] = mapped_column(Integer, default=0)
    authority_score: Mapped[int] = mapped_column(Integer, default=0)
    freshness_score: Mapped[int] = mapped_column(Integer, default=0)
    consistency_score: Mapped[int] = mapped_column(Integer, default=0)
    corroboration_score: Mapped[int] = mapped_column(Integer, default=0)
    evidence_confidence: Mapped[int] = mapped_column(Integer, default=0)

    # Syndicated copies of the same underlying evidence share this group id, so
    # 10 URLs of one job are NOT 10 independent confirmations.
    independence_group_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)

    verification_status: Mapped[VerificationStatus] = mapped_column(
        SAEnum(VerificationStatus, native_enum=False, length=24), default=VerificationStatus.UNVERIFIED, index=True
    )
    verification_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    verification_version: Mapped[str] = mapped_column(String(16), default="0")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)


class EvidenceConflict(Base):
    """A detected conflict between two pieces of evidence. Never silently
    discarded — the stronger/authoritative evidence is preferred explicitly."""

    __tablename__ = "evidence_conflicts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    subject_type: Mapped[str] = mapped_column(String(32), default="LEAD")   # LEAD | SIGNAL | COMPANY | JOB
    subject_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    evidence_id_a: Mapped[int | None] = mapped_column(Integer, nullable=True)
    evidence_id_b: Mapped[int | None] = mapped_column(Integer, nullable=True)
    conflict_type: Mapped[ConflictType] = mapped_column(
        SAEnum(ConflictType, native_enum=False, length=32), default=ConflictType.OTHER
    )
    severity: Mapped[ConflictSeverity] = mapped_column(
        SAEnum(ConflictSeverity, native_enum=False, length=16), default=ConflictSeverity.LOW
    )
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    resolution_status: Mapped[EvidenceResolutionStatus] = mapped_column(
        SAEnum(EvidenceResolutionStatus, native_enum=False, length=16), default=EvidenceResolutionStatus.UNRESOLVED
    )
    preferred_evidence_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    data_provenance: Mapped[DataProvenance] = mapped_column(
        SAEnum(DataProvenance, native_enum=False, length=16), default=DataProvenance.REAL
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), default=utcnow)


class EvidenceClaim(Base):
    """A specific claim (e.g. 'ABC is hiring Java developers') with the evidence
    supporting or contradicting it. Claims are never created without evidence."""

    __tablename__ = "evidence_claims"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    subject_type: Mapped[str] = mapped_column(String(32), default="LEAD")
    subject_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    claim_type: Mapped[str] = mapped_column(String(48), default="OTHER")
    claim_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    evidence_ids: Mapped[list[int]] = mapped_column(JSON, default=list)
    claim_confidence: Mapped[int] = mapped_column(Integer, default=0)
    verification_status: Mapped[VerificationStatus] = mapped_column(
        SAEnum(VerificationStatus, native_enum=False, length=24), default=VerificationStatus.UNVERIFIED
    )
    supporting_sources: Mapped[list[str]] = mapped_column(JSON, default=list)
    contradictory_sources: Mapped[list[str]] = mapped_column(JSON, default=list)
    data_provenance: Mapped[DataProvenance] = mapped_column(
        SAEnum(DataProvenance, native_enum=False, length=16), default=DataProvenance.REAL
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), default=utcnow)


class Company(Base):
    """Canonical company entity — the resolved identity multiple source records
    map to. Unknown facts stay NULL; identity/evidence confidence are explicit and
    separate. Raw source names are preserved via CompanySourceReference."""

    __tablename__ = "companies"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    canonical_name: Mapped[str] = mapped_column(String(255), nullable=False)
    legal_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    normalized_name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    website: Mapped[str | None] = mapped_column(String(512), nullable=True)
    primary_domain: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    alternate_domains: Mapped[list[str]] = mapped_column(JSON, default=list)

    industry: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    sub_industry: Mapped[str | None] = mapped_column(String(128), nullable=True)
    company_type: Mapped[CompanyType | None] = mapped_column(
        SAEnum(CompanyType, native_enum=False, length=32), nullable=True
    )
    company_types: Mapped[list[str]] = mapped_column(JSON, default=list)  # may have several

    headquarters_country: Mapped[str | None] = mapped_column(String(64), nullable=True)
    headquarters_state: Mapped[str | None] = mapped_column(String(64), nullable=True)
    headquarters_city: Mapped[str | None] = mapped_column(String(128), nullable=True)
    india_presence: Mapped[bool | None] = mapped_column(nullable=True)
    india_locations: Mapped[list[str]] = mapped_column(JSON, default=list)

    company_size_band: Mapped[str | None] = mapped_column(String(32), nullable=True)
    employee_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    employee_count_source: Mapped[str | None] = mapped_column(String(128), nullable=True)
    founded_year: Mapped[int | None] = mapped_column(Integer, nullable=True)
    public_company: Mapped[bool | None] = mapped_column(nullable=True)
    parent_company_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)

    source_status: Mapped[str | None] = mapped_column(String(32), nullable=True)
    identity_confidence: Mapped[int] = mapped_column(Integer, default=0)
    evidence_confidence: Mapped[int] = mapped_column(Integer, default=0)
    verification_status: Mapped[VerificationStatus] = mapped_column(
        SAEnum(VerificationStatus, native_enum=False, length=24), default=VerificationStatus.UNVERIFIED, index=True
    )
    data_provenance: Mapped[DataProvenance] = mapped_column(
        SAEnum(DataProvenance, native_enum=False, length=16), default=DataProvenance.REAL, index=True
    )
    first_seen_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)

    source_references: Mapped[list["CompanySourceReference"]] = relationship(
        back_populates="company", cascade="all, delete-orphan", lazy="selectin"
    )


class CompanyRelationship(Base):
    """A parent/subsidiary/brand/etc. relationship. Only created with evidence —
    ownership/acquisitions are never inferred."""

    __tablename__ = "company_relationships"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    from_company_id: Mapped[int] = mapped_column(ForeignKey("companies.id", ondelete="CASCADE"), index=True)
    to_company_id: Mapped[int] = mapped_column(ForeignKey("companies.id", ondelete="CASCADE"), index=True)
    relationship_type: Mapped[CompanyRelationshipType] = mapped_column(
        SAEnum(CompanyRelationshipType, native_enum=False, length=24), default=CompanyRelationshipType.RELATED_TO
    )
    evidence: Mapped[str | None] = mapped_column(Text, nullable=True)
    confidence: Mapped[int] = mapped_column(Integer, default=0)
    source: Mapped[str | None] = mapped_column(String(128), nullable=True)
    data_provenance: Mapped[DataProvenance] = mapped_column(
        SAEnum(DataProvenance, native_enum=False, length=16), default=DataProvenance.REAL
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), default=utcnow)


class CompanySourceReference(Base):
    """How one source represented a company. Never overwritten — every source's
    original representation is preserved as evidence."""

    __tablename__ = "company_source_references"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id", ondelete="CASCADE"), index=True)
    source_name: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    source_category: Mapped[str | None] = mapped_column(String(64), nullable=True)
    source_url: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    source_record_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    observed_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    observed_domain: Mapped[str | None] = mapped_column(String(255), nullable=True)
    observed_location: Mapped[str | None] = mapped_column(String(255), nullable=True)
    source_status: Mapped[str | None] = mapped_column(String(32), nullable=True)
    evidence_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    confidence: Mapped[int] = mapped_column(Integer, default=0)
    first_seen_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    company: Mapped["Company"] = relationship(back_populates="source_references")


class CompanyResolutionCandidate(Base):
    """An uncertain entity-resolution decision held for human review — never
    silently merged."""

    __tablename__ = "company_resolution_candidates"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    observed_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    observed_domain: Mapped[str | None] = mapped_column(String(255), nullable=True)
    observed_location: Mapped[str | None] = mapped_column(String(255), nullable=True)
    candidate_company_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    match_status: Mapped[CompanyMatchStatus] = mapped_column(
        SAEnum(CompanyMatchStatus, native_enum=False, length=24), default=CompanyMatchStatus.REVIEW_REQUIRED
    )
    confidence: Mapped[int] = mapped_column(Integer, default=0)
    matching_factors: Mapped[list[str]] = mapped_column(JSON, default=list)
    conflicting_factors: Mapped[list[str]] = mapped_column(JSON, default=list)
    resolution_explanation: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[CompanyResolutionDecision] = mapped_column(
        SAEnum(CompanyResolutionDecision, native_enum=False, length=16),
        default=CompanyResolutionDecision.PENDING, index=True,
    )
    data_provenance: Mapped[DataProvenance] = mapped_column(
        SAEnum(DataProvenance, native_enum=False, length=16), default=DataProvenance.REAL, index=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), default=utcnow)


class CompanyEvent(Base):
    """A meaningful change in a company's intelligence (history / audit trail).
    Powers "why did this become a HOT lead?"."""

    __tablename__ = "company_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id", ondelete="CASCADE"), index=True)
    event_type: Mapped[str] = mapped_column(String(48), index=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    old_value: Mapped[str | None] = mapped_column(String(255), nullable=True)
    new_value: Mapped[str | None] = mapped_column(String(255), nullable=True)
    data_provenance: Mapped[DataProvenance] = mapped_column(
        SAEnum(DataProvenance, native_enum=False, length=16), default=DataProvenance.REAL
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), default=utcnow)
