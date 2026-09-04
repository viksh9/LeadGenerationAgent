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
    industry: Mapped[str | None] = mapped_column(String(128), nullable=True)
    location: Mapped[str | None] = mapped_column(String(255), nullable=True)
    company_size: Mapped[str | None] = mapped_column(String(64), nullable=True)
    company_website: Mapped[str | None] = mapped_column(String(255), nullable=True)

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
