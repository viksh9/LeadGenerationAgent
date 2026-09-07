"""Pydantic v2 schema layer for the HTTP API (Phase 1).

These schemas are the contract for FastAPI request validation and responses, and
are designed to be consumed by a future React + TypeScript frontend: consistent
field names, flat/predictable JSON, ISO-8601 timestamps, and enum values that
serialize to clear strings (e.g. "HOT", "HIRING").

Enums are reused from the database layer — not redefined here.
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Any, Optional

from pydantic import (
    AfterValidator,
    BaseModel,
    ConfigDict,
    Field,
    HttpUrl,
    TypeAdapter,
    field_validator,
)

from database.models import (
    CompanyType,
    DataProvenance,
    HiringIntensity,
    LeadPriority,
    LeadStatus,
    SignalType,
)

# ---------------------------------------------------------------------------
# Reusable validators / annotated types
# ---------------------------------------------------------------------------

_URL_ADAPTER = TypeAdapter(HttpUrl)


def _validate_optional_url(value: Optional[str]) -> Optional[str]:
    """Validate a URL when supplied; treat empty/whitespace as not supplied.

    Returns the original string (so it persists cleanly to a String column)
    rather than a pydantic Url object.
    """
    if value is None:
        return None
    text = value.strip() if isinstance(value, str) else str(value)
    if not text:
        return None
    _URL_ADAPTER.validate_python(text)  # raises ValidationError if invalid
    return text


def _validate_required_name(value: str) -> str:
    text = (value or "").strip()
    if not text:
        raise ValueError("company_name must not be empty or whitespace")
    return text


def _validate_optional_name(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    return _validate_required_name(value)


OptionalUrl = Annotated[Optional[str], AfterValidator(_validate_optional_url)]


# ---------------------------------------------------------------------------
# Shared writable fields (everything a client may set on a lead)
# ---------------------------------------------------------------------------


class _LeadWritableFields(BaseModel):
    """Fields common to create/update/analyze. Calculated fields are excluded."""

    industry: Optional[str] = None
    location: Optional[str] = None

    signal_title: Optional[str] = None
    signal_description: Optional[str] = None
    signal_date: Optional[datetime] = None
    source_name: Optional[str] = None
    source_url: OptionalUrl = None

    technologies: list[str] = Field(default_factory=list)
    project_name: Optional[str] = None
    project_value: Optional[float] = Field(default=None, ge=0)
    estimated_hiring: Optional[int] = Field(default=None, ge=0)
    hiring_roles: list[str] = Field(default_factory=list)

    company_size: Optional[str] = None
    company_website: OptionalUrl = None

    poc_name: Optional[str] = None
    poc_title: Optional[str] = None
    poc_linkedin_url: OptionalUrl = None
    public_contact: Optional[str] = None

    signal_confidence: Optional[float] = Field(default=None, ge=0, le=100)


# ---------------------------------------------------------------------------
# Requests
# ---------------------------------------------------------------------------


class LeadCreate(_LeadWritableFields):
    """Input for creating a lead. Rejects unknown/calculated fields."""

    model_config = ConfigDict(extra="forbid")

    company_name: str
    signal_type: Optional[SignalType] = None
    status: LeadStatus = LeadStatus.NEW

    @field_validator("company_name")
    @classmethod
    def _check_company_name(cls, value: str) -> str:
        return _validate_required_name(value)


class LeadUpdate(_LeadWritableFields):
    """Partial update. All fields optional; unknown/calculated fields rejected."""

    model_config = ConfigDict(extra="forbid")

    company_name: Optional[str] = None
    signal_type: Optional[SignalType] = None
    status: Optional[LeadStatus] = None

    @field_validator("company_name")
    @classmethod
    def _check_company_name(cls, value: Optional[str]) -> Optional[str]:
        return _validate_optional_name(value)


class LeadAnalyzeRequest(_LeadWritableFields):
    """Raw signal input for the analysis pipeline (raw signal -> calculated lead).

    Calculated fields are never required here; unknown extras are ignored so raw
    payloads from varied sources are accepted leniently.
    """

    model_config = ConfigDict(extra="ignore")

    company_name: str

    @field_validator("company_name")
    @classmethod
    def _check_company_name(cls, value: str) -> str:
        return _validate_required_name(value)


# ---------------------------------------------------------------------------
# Responses
# ---------------------------------------------------------------------------


class LeadResponse(BaseModel):
    """A complete stored lead, including pipeline-calculated fields."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    company_name: str
    normalized_company_name: Optional[str] = None
    company_domain: Optional[str] = None
    company_type: Optional[CompanyType] = None
    industry: Optional[str] = None
    location: Optional[str] = None

    # Company-level hiring aggregation.
    it_job_count: int = 0
    recent_job_count: int = 0
    hiring_intensity: Optional[HiringIntensity] = None
    primary_target_role: Optional[str] = None
    company_signals: list[str] = Field(default_factory=list)

    signal_type: Optional[SignalType] = None
    signal_title: Optional[str] = None
    signal_description: Optional[str] = None
    signal_date: Optional[datetime] = None
    source_name: Optional[str] = None
    source_url: Optional[str] = None

    technologies: list[str] = Field(default_factory=list)
    project_name: Optional[str] = None
    project_value: Optional[float] = None
    estimated_hiring: Optional[int] = None
    hiring_roles: list[str] = Field(default_factory=list)

    company_size: Optional[str] = None
    company_website: Optional[str] = None

    poc_name: Optional[str] = None
    poc_title: Optional[str] = None
    poc_linkedin_url: Optional[str] = None
    public_contact: Optional[str] = None

    signal_confidence: Optional[float] = None
    lead_score: float = 0.0
    lead_priority: LeadPriority = LeadPriority.LOW

    opportunity_summary: Optional[str] = None
    recommended_action: Optional[str] = None
    recommended_pitch: Optional[str] = None

    # Evidence / provenance.
    data_provenance: DataProvenance = DataProvenance.REAL
    source_count: int = 0
    evidence: list[dict] = Field(default_factory=list)
    last_signal_date: Optional[datetime] = None

    status: LeadStatus = LeadStatus.NEW
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    last_verified_at: Optional[datetime] = None


class TechnologyDemandItem(BaseModel):
    """Aggregated demand for one technology across collected IT jobs."""

    technology: str
    openings: int
    companies: int


class TechnologyDemandResponse(BaseModel):
    """Technology demand computed from real (or synthetic) collected job records."""

    provenance: DataProvenance | None = None
    items: list[TechnologyDemandItem] = Field(default_factory=list)


class LeadListResponse(BaseModel):
    """A page of leads with pagination metadata."""

    items: list[LeadResponse] = Field(default_factory=list)
    total: int = 0
    page: int = 1
    page_size: int = 20
    total_pages: int = 0


# ---------------------------------------------------------------------------
# Analysis response (shape only — the pipeline that fills it is a later phase)
# ---------------------------------------------------------------------------


class AnalyzedSignal(BaseModel):
    signal_type: Optional[SignalType] = None
    title: str
    description: Optional[str] = None
    strength: float = 0.0
    buying_stage: Optional[str] = None
    intent_tags: list[str] = Field(default_factory=list)


class OpportunityAnalysis(BaseModel):
    summary: str
    recommended_motion: Optional[str] = None
    primary_stage: Optional[str] = None
    pain_hypotheses: list[str] = Field(default_factory=list)


class POCRecommendation(BaseModel):
    full_name: str
    title: Optional[str] = None
    email: Optional[str] = None
    linkedin_url: Optional[str] = None
    seniority: Optional[str] = None
    is_decision_maker: bool = False
    confidence: float = 0.0


class ScoreComponent(BaseModel):
    label: str
    points: float


class LeadAnalyzeResponse(BaseModel):
    """Result of analyzing a raw signal — frontend-friendly, flat where possible."""

    lead: LeadResponse
    signals_detected: list[AnalyzedSignal] = Field(default_factory=list)
    opportunity_analysis: Optional[OpportunityAnalysis] = None
    poc_recommendation: Optional[POCRecommendation] = None
    score: float = 0.0
    priority: LeadPriority = LeadPriority.LOW
    score_breakdown: list[ScoreComponent] = Field(default_factory=list)
    recommended_action: Optional[str] = None
    recommended_pitch: Optional[str] = None


# ---------------------------------------------------------------------------
# Health / error envelopes
# ---------------------------------------------------------------------------


class HealthResponse(BaseModel):
    status: str
    app: str
    environment: str = "development"
    version: str = "0.1.0"


class ErrorDetail(BaseModel):
    code: str
    message: str


class ErrorBody(BaseModel):
    error: ErrorDetail
