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
    LeadReadiness,
    LeadStatus,
    SignalType,
    SourceTier,
    VerificationStatus,
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

    # Verification intelligence — kept separate from lead_score/lead_priority.
    source_reliability: int = 0
    evidence_confidence: int = 0
    freshness_score: int = 0
    independent_support_count: int = 0
    verification_status: VerificationStatus = VerificationStatus.UNVERIFIED
    lead_readiness: LeadReadiness = LeadReadiness.REVIEW_REQUIRED
    verification_reason: Optional[str] = None
    verified_at: Optional[datetime] = None

    status: LeadStatus = LeadStatus.NEW
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    last_verified_at: Optional[datetime] = None


class CompanyResponse(BaseModel):
    """A canonical company entity (list/detail)."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    canonical_name: str
    legal_name: Optional[str] = None
    normalized_name: str
    primary_domain: Optional[str] = None
    website: Optional[str] = None
    industry: Optional[str] = None
    company_type: Optional[CompanyType] = None
    company_types: list[str] = Field(default_factory=list)
    headquarters_city: Optional[str] = None
    india_presence: Optional[bool] = None
    india_locations: list[str] = Field(default_factory=list)
    identity_confidence: int = 0
    evidence_confidence: int = 0
    verification_status: VerificationStatus = VerificationStatus.UNVERIFIED
    data_provenance: DataProvenance = DataProvenance.REAL


class CompanyListResponse(BaseModel):
    items: list[CompanyResponse] = Field(default_factory=list)
    total: int = 0
    page: int = 1
    page_size: int = 20
    total_pages: int = 0


class ResolutionCandidateResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    observed_name: Optional[str] = None
    observed_domain: Optional[str] = None
    candidate_company_id: Optional[int] = None
    match_status: str
    confidence: int = 0
    matching_factors: list[str] = Field(default_factory=list)
    conflicting_factors: list[str] = Field(default_factory=list)
    resolution_explanation: Optional[str] = None
    status: str
    data_provenance: DataProvenance = DataProvenance.REAL


class ResolutionDecisionRequest(BaseModel):
    decision: str = Field(description="MERGE | KEEP_SEPARATE | IGNORE")


class EvidenceResponse(BaseModel):
    """One evidence record supporting a lead/signal."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    evidence_type: str
    source_name: Optional[str] = None
    source_url: Optional[str] = None
    source_domain: Optional[str] = None
    source_tier: SourceTier = SourceTier.TIER_4
    evidence_title: Optional[str] = None
    published_at: Optional[datetime] = None
    observed_at: Optional[datetime] = None
    source_reliability_score: int = 0
    freshness_score: int = 0
    evidence_confidence: int = 0
    independence_group_id: Optional[str] = None
    verification_status: VerificationStatus = VerificationStatus.UNVERIFIED
    data_provenance: DataProvenance = DataProvenance.REAL


class ConflictResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    conflict_type: str
    severity: str
    description: Optional[str] = None
    resolution_status: str


class VerificationResponse(BaseModel):
    """The four distinct scores + verification status for a lead."""

    lead_id: int
    company_name: str
    # Kept SEPARATE — never collapsed into one number.
    lead_score: float
    lead_priority: LeadPriority
    source_reliability: int
    evidence_confidence: int
    signal_confidence: Optional[float] = None
    freshness_score: int
    verification_status: VerificationStatus
    lead_readiness: LeadReadiness
    independent_support_count: int
    source_count: int
    verification_reason: Optional[str] = None
    verified_at: Optional[datetime] = None
    supporting_sources: list[EvidenceResponse] = Field(default_factory=list)
    conflicts: list[ConflictResponse] = Field(default_factory=list)
    data_provenance: DataProvenance = DataProvenance.REAL


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


# ---------------------------------------------------------------------------
# Real-data source connectivity status
# ---------------------------------------------------------------------------


class SourceStatusResponse(BaseModel):
    """Truthful runtime status of one catalogued real-data source.

    ``status`` is the configuration-level readiness (NOT_CONFIGURED / CONFIGURED /
    REQUIRES_REVIEW / PLANNED / …). ``connection_status`` is the outcome of the
    LAST real connectivity check (or null if never checked) — only it can say
    CONNECTED, and only after a real request succeeded. Never exposes credentials.
    """

    model_config = ConfigDict(from_attributes=True)

    source_id: str
    name: str
    category: str
    source_type: str
    provider: Optional[str] = None
    collector_implemented: bool
    requires_api_key: bool
    authentication_type: str = "NONE"
    credential_env_vars: list[str] = Field(default_factory=list)
    capabilities: list[str] = Field(default_factory=list)
    supports_india: bool = False
    reliability_tier: Optional[str] = None
    status: str
    detail: str
    priority: int
    commercial_use_status: str
    documentation_url: Optional[str] = None
    terms_url: Optional[str] = None
    # Persisted connectivity health (from the last real check).
    connection_status: Optional[str] = None
    last_checked_at: Optional[datetime] = None
    last_success_at: Optional[datetime] = None
    last_failure_at: Optional[datetime] = None
    last_error: Optional[str] = None
    # Ingestion metrics (from the last collection run for this source).
    last_ingestion_at: Optional[datetime] = None
    last_ingestion_records_fetched: Optional[int] = None
    last_ingestion_records_persisted: Optional[int] = None


class SourceStatusListResponse(BaseModel):
    """Source connectivity overview. ``any_connected`` is only ever true after a
    real source has been verified live — never from configuration alone."""

    data_mode: str = "REAL_ONLY"
    items: list[SourceStatusResponse]
    total: int
    connected_count: int
    configured_count: int
    any_connected: bool


class SourceCheckResponse(BaseModel):
    """Result of an on-demand real connectivity check for one source."""

    source_id: str
    connection_status: str
    message: Optional[str] = None
    performed_request: bool
    checked_at: datetime


# ---------------------------------------------------------------------------
# Official company career / ATS sources
# ---------------------------------------------------------------------------


class CareerSourceResponse(BaseModel):
    """A discovered official company career / ATS source (Greenhouse, Lever, …)."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    company_id: Optional[int] = None
    company_name: Optional[str] = None
    ats_provider: str
    board_identifier: Optional[str] = None
    careers_url: Optional[str] = None
    discovery_method: Optional[str] = None
    status: str
    enabled: bool = False
    evidence_tier: str = "TIER_1"          # official company source
    last_checked_at: Optional[datetime] = None
    last_success_at: Optional[datetime] = None
    last_error: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    @field_validator("ats_provider", "status", mode="before")
    @classmethod
    def _enum_value(cls, v):
        return v.value if hasattr(v, "value") else v


class CareerSourceListResponse(BaseModel):
    items: list[CareerSourceResponse]
    total: int


class DiscoverAdhocRequest(BaseModel):
    """Ad-hoc career/ATS discovery from a provided company name + its official
    domain or careers URL. No stored Company entity is required — this is a live,
    SSRF-safe lookup of the domain the caller supplies; nothing is persisted."""

    company_name: str = Field(..., min_length=1, max_length=255)
    domain: Optional[str] = Field(default=None, max_length=255)
    careers_url: Optional[str] = Field(default=None, max_length=1024)


class DiscoverCareerSourceResponse(BaseModel):
    """Result of a company→ATS discovery attempt (real, safe fetch)."""

    company_id: Optional[int] = None
    company_name: Optional[str] = None
    found: bool
    verified: bool
    provider: Optional[str] = None
    board_identifier: Optional[str] = None
    careers_url: Optional[str] = None
    discovery_method: Optional[str] = None
    detail: str
    career_source: Optional[CareerSourceResponse] = None


class CareerSourceCollectResponse(BaseModel):
    """Result of a real collection run for one career source."""

    source_id: int
    provider: str
    board_identifier: Optional[str] = None
    status: str
    requests: int = 0
    records_fetched: int = 0
    records_persisted: int = 0
    canonical_jobs_created: int = 0
    leads_created: int = 0
    leads_updated: int = 0
    message: Optional[str] = None


# ---------------------------------------------------------------------------
# Business signals, tenders, company timeline
# ---------------------------------------------------------------------------


def _enum_val(v):
    return v.value if hasattr(v, "value") else v


class SignalResponse(BaseModel):
    """A real business/market signal (project, contract, tender, expansion, …)."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    company_id: Optional[int] = None
    company_name: Optional[str] = None
    signal_type: str
    signal_title: Optional[str] = None
    signal_description: Optional[str] = None
    signal_url: Optional[str] = None
    published_at: Optional[datetime] = None
    technologies: list[str] = Field(default_factory=list)
    location: Optional[str] = None
    signal_strength: str
    source_id: str
    source_count: int = 1
    evidence_confidence: int = 0
    commercial_intent: str = "UNKNOWN"
    data_provenance: str = "REAL"

    @field_validator("signal_type", "signal_strength", "commercial_intent", "data_provenance", mode="before")
    @classmethod
    def _ev(cls, v):
        return _enum_val(v)


class SignalListResponse(BaseModel):
    items: list[SignalResponse]
    total: int
    page: int = 1
    page_size: int = 20
    total_pages: int = 0


class TenderResponse(BaseModel):
    """A government/procurement tender or RFP (real source only)."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    source_id: str
    source_record_id: Optional[str] = None
    title: Optional[str] = None
    organization_name: Optional[str] = None
    department: Optional[str] = None
    organization_type: Optional[str] = None
    location: Optional[str] = None
    issue_date: Optional[datetime] = None
    publication_date: Optional[datetime] = None
    closing_date: Optional[datetime] = None
    award_date: Optional[datetime] = None
    estimated_value: Optional[float] = None
    currency: Optional[str] = None
    estimated_value_text: Optional[str] = None
    category: Optional[str] = None
    technologies: list[str] = Field(default_factory=list)
    scope_summary: Optional[str] = None
    tender_status: str
    source_url: Optional[str] = None
    company_id: Optional[int] = None
    target_company_id: Optional[int] = None
    signal_origin_organization: Optional[str] = None
    evidence_confidence: int = 0
    freshness_score: int = 0
    commercial_intent: str = "UNKNOWN"
    data_provenance: str = "REAL"
    first_seen_at: Optional[datetime] = None
    last_seen_at: Optional[datetime] = None

    @field_validator("tender_status", "commercial_intent", "data_provenance", mode="before")
    @classmethod
    def _ev(cls, v):
        return _enum_val(v)


class TenderListResponse(BaseModel):
    items: list[TenderResponse]
    total: int
    page: int = 1
    page_size: int = 20
    total_pages: int = 0


class TimelineEventResponse(BaseModel):
    date: Optional[datetime] = None
    category: str
    event_type: str
    title: str
    detail: Optional[str] = None
    source: Optional[str] = None
    source_url: Optional[str] = None


class TimelineResponse(BaseModel):
    company_id: int
    events: list[TimelineEventResponse]
    total: int


# ---------------------------------------------------------------------------
# Decision makers / contacts / stakeholders
# ---------------------------------------------------------------------------


class DecisionMakerResponse(BaseModel):
    """A REAL person or business contact (source-backed; never fabricated)."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    company_id: Optional[int] = None
    company_name: Optional[str] = None
    full_name: Optional[str] = None
    job_title: Optional[str] = None
    normalized_role: Optional[str] = None
    role_category: str = "OTHER"
    department: Optional[str] = None
    seniority: Optional[str] = None
    profile_url: Optional[str] = None
    professional_network_url: Optional[str] = None
    business_email: Optional[str] = None
    business_phone: Optional[str] = None
    contact_type: str = "OTHER"
    email_status: Optional[str] = None
    contact_source: Optional[str] = None
    source_type: Optional[str] = None
    source_url: Optional[str] = None
    identity_confidence: int = 0
    role_confidence: int = 0
    company_confidence: int = 0
    contact_confidence: int = 0
    evidence_confidence: int = 0
    freshness_score: int = 0
    verification_status: str = "UNVERIFIED"
    match_status: str = "NO_MATCH"
    data_provenance: str = "REAL"
    last_verified_at: Optional[datetime] = None

    @field_validator("role_category", "contact_type", "email_status", "verification_status",
                     "match_status", "data_provenance", mode="before")
    @classmethod
    def _ev(cls, v):
        return v.value if hasattr(v, "value") else v


class DecisionMakerListResponse(BaseModel):
    items: list[DecisionMakerResponse]
    total: int
    page: int = 1
    page_size: int = 20
    total_pages: int = 0


class StakeholderRoleResponse(BaseModel):
    role: str
    role_category: str
    decision_maker_type: str
    relevance_score: int
    reason: str
    is_primary: bool = False


class LeadStakeholdersResponse(BaseModel):
    """Recommended ROLES (no person) + any VERIFIED people/contacts, kept distinct."""

    lead_id: int
    company_name: Optional[str] = None
    recommended_roles: list[StakeholderRoleResponse]
    recommendation_confidence: int = 0
    verified_decision_makers: list[DecisionMakerResponse] = Field(default_factory=list)
    business_contacts: list[DecisionMakerResponse] = Field(default_factory=list)
    outreach_readiness: str = "RESEARCH_REQUIRED"
    outreach_reasons: list[str] = Field(default_factory=list)


# --- ContactOut POC discovery/enrichment (Prompt 44) ----------------------- #
class POCResponse(DecisionMakerResponse):
    """A ContactOut-discovered POC. Adds the ranking match score and the contact
    TRUST (reliability of the contact match — distinct from the business lead score).
    Contact fields are only ever the real values ContactOut returned (never fabricated)."""

    company_domain: Optional[str] = None
    match_score: int = 0
    contact_trust_score: int = 0
    contact_trust_status: Optional[str] = None
    is_current: bool = True
    employment_status: Optional[str] = None   # CURRENT_VERIFIED / CURRENT_LIKELY / FORMER / UNKNOWN


class POCDiscoveryResponse(BaseModel):
    """Result of a company-level POC discovery run. Honest states only — a failure
    never yields a fabricated POC."""

    lead_id: Optional[int] = None
    company_id: Optional[int] = None
    company_name: Optional[str] = None
    status: str                       # ENRICHED | CACHED | NO_POC_FOUND | NOT_CONFIGURED | RATE_LIMITED | UNAVAILABLE
    candidates_found: int = 0
    searches_used: int = 0
    enrichments_used: int = 0
    persisted: int = 0
    reason: str = ""
    error_code: Optional[str] = None
    pocs: list[POCResponse] = Field(default_factory=list)


class POCListResponse(BaseModel):
    """POCs for a lead: real people (when discovered/verified) plus role-only
    recommendations (never presented as real people)."""

    lead_id: int
    company_name: Optional[str] = None
    contactout_status: str            # config status (NOT a live check)
    pocs: list[POCResponse] = Field(default_factory=list)
    recommended_roles: list[StakeholderRoleResponse] = Field(default_factory=list)
    recommendation_confidence: int = 0
    note: Optional[str] = None


class PublicIntelligenceDiscoveryResponse(BaseModel):
    """Result of a free/public intelligence discovery run. Honest states only."""

    lead_id: Optional[int] = None
    company_id: Optional[int] = None
    company_name: Optional[str] = None
    status: str                       # ENRICHED | CACHED | NO_POC_FOUND | DISABLED
    people_found: int = 0
    persisted: int = 0
    provider_status: dict[str, str] = Field(default_factory=dict)
    company_facts_updated: list[str] = Field(default_factory=list)
    reason: str = ""
    pocs: list[POCResponse] = Field(default_factory=list)


class CompanyLocationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    address_line_1: Optional[str] = None
    address_line_2: Optional[str] = None
    city: Optional[str] = None
    state_or_region: Optional[str] = None
    postal_code: Optional[str] = None
    country: Optional[str] = None
    full_address: Optional[str] = None
    location_type: str = "UNKNOWN"
    is_headquarters: bool = False
    source: Optional[str] = None
    source_url: Optional[str] = None
    trust_score: int = 0


class CompanyFieldSourceResponse(BaseModel):
    """Field-level provenance for the Company Intelligence / Sources UI (§28)."""

    model_config = ConfigDict(from_attributes=True)

    field: str
    value: Optional[str] = None
    source: Optional[str] = None
    source_type: Optional[str] = None
    source_url: Optional[str] = None
    evidence_text: Optional[str] = None
    trust_score: int = 0
    retrieved_at: Optional[datetime] = None


class CompanyOfficerResponse(BaseModel):
    """A LEGAL officer/director (§12/§13) — never a sales/technical POC."""

    model_config = ConfigDict(from_attributes=True)

    name: Optional[str] = None
    position: Optional[str] = None
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    role_kind: str = "LEGAL_OFFICER"
    source: Optional[str] = None
    source_url: Optional[str] = None


class CompanyPublicIntelligenceResponse(BaseModel):
    """Company profile facts (with sources) + real public leadership (§27/§28)."""

    company_id: int
    company_name: str
    website: Optional[str] = None
    linkedin_url: Optional[str] = None
    github_url: Optional[str] = None
    industry: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    country: Optional[str] = None
    full_address: Optional[str] = None
    postal_code: Optional[str] = None
    company_phone: Optional[str] = None
    company_email: Optional[str] = None
    contact_url: Optional[str] = None
    careers_url: Optional[str] = None
    leadership_url: Optional[str] = None
    wikidata_id: Optional[str] = None
    # Legal / company verification (OpenCorporates, §7/§30) — distinct from operating brand.
    legal_name: Optional[str] = None
    company_number: Optional[str] = None
    jurisdiction_code: Optional[str] = None
    company_status: Optional[str] = None
    incorporation_date: Optional[str] = None
    registry_url: Optional[str] = None
    opencorporates_url: Optional[str] = None
    registered_address: Optional[str] = None
    india_entity_type: Optional[str] = None
    data_trust_score: int = 0
    official_verified_at: Optional[datetime] = None
    india_locations: list[str] = Field(default_factory=list)
    locations: list[CompanyLocationResponse] = Field(default_factory=list)
    officers: list[CompanyOfficerResponse] = Field(default_factory=list)
    field_sources: list[CompanyFieldSourceResponse] = Field(default_factory=list)
    public_leadership: list[POCResponse] = Field(default_factory=list)


class OpenCorporatesStatusResponse(BaseModel):
    """Admin diagnostics for OpenCorporates (§40). Never exposes the token."""

    status: str                       # CONFIGURED | NOT_CONFIGURED | DISABLED
    api_version: str
    last_success_at: Optional[str] = None
    last_error: Optional[str] = None
    data_ttl_days: int = 0


class CompanyIntelDiscoveryResponse(BaseModel):
    """Result of a company-level official-intelligence discovery run (§39)."""

    company_id: int
    company_name: str
    status: str                       # SUCCESS | PARTIAL | SOURCE_UNAVAILABLE | ERROR
    provider_status: dict[str, str] = Field(default_factory=dict)
    fields_updated: list[str] = Field(default_factory=list)
    people_persisted: int = 0
    data_trust_score: int = 0
    reason: str = ""


class PublicIntelligenceTestResponse(BaseModel):
    """Real connectivity check against a configured public source (§36)."""

    provider: str
    result: str                       # LIVE_VERIFIED | NOT_CONFIGURED | SOURCE_UNAVAILABLE | ERROR
    status: str
    message: Optional[str] = None
    performed_request: bool
    checked_at: datetime


class ContactOutStatusResponse(BaseModel):
    """ContactOut integration config status for the Settings UI. Never exposes the
    token or base URL."""

    status: str                       # NOT_CONFIGURED | CONFIGURED | DISABLED
    configured: bool
    note: str
    people_search_rate_per_minute: int
    other_rate_per_minute: int
    max_poc_searches_per_opportunity: int
    max_enrichments_per_opportunity: int
    cache_ttl_hours: int


class EnrichRunResponse(BaseModel):
    """Result of a real official-source enrichment run for one company."""

    company_id: int
    provider: str
    people_found: int = 0
    contacts_found: int = 0
    people_accepted: int = 0
    contacts_accepted: int = 0
    duplicates: int = 0
    pages_fetched: int = 0
    message: Optional[str] = None


# ---------------------------------------------------------------------------
# AI reasoning layer
# ---------------------------------------------------------------------------


class AIClaimResponse(BaseModel):
    claim_text: str
    claim_type: str = "INFERENCE"
    support_level: str = "SUPPORTED_INFERENCE"
    evidence_ids: list[int] = Field(default_factory=list)
    validation_status: Optional[str] = None


class AIIntelligenceResponse(BaseModel):
    """AI (or deterministic-baseline) reasoning over real data. Facts and inferences
    are kept distinct; AI confidence is separate from lead_score/evidence_confidence."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    subject_type: str
    subject_id: int
    company_id: Optional[int] = None
    lead_id: Optional[int] = None
    executive_summary: Optional[str] = None
    opportunity_explanation: Optional[str] = None
    urgency_reason: Optional[str] = None
    business_problem_hypothesis: Optional[str] = None
    recommended_action: Optional[str] = None
    next_best_action: Optional[str] = None
    sales_angle: Optional[str] = None
    sales_pitch: Optional[str] = None
    verified_facts: list[AIClaimResponse] = Field(default_factory=list)
    inferred_insights: list[AIClaimResponse] = Field(default_factory=list)
    unknowns: list[str] = Field(default_factory=list)
    risk_flags: list[str] = Field(default_factory=list)
    target_roles: list[str] = Field(default_factory=list)
    evidence_ids: list[int] = Field(default_factory=list)
    source_ids: list[str] = Field(default_factory=list)
    confidence: int = 0
    analysis_status: str = "DETERMINISTIC"
    ai_generated: bool = False
    unsupported_claim_count: int = 0
    provider: Optional[str] = None
    model_name: Optional[str] = None
    prompt_version: Optional[str] = None
    generated_at: Optional[datetime] = None

    @field_validator("analysis_status", mode="before")
    @classmethod
    def _ev(cls, v):
        return v.value if hasattr(v, "value") else v


class AIStatusResponse(BaseModel):
    """Truthful AI provider status. CONNECTED only after a real model request."""

    provider: Optional[str] = None
    model: Optional[str] = None
    status: str = "NOT_CONFIGURED"
    deterministic_baseline_available: bool = True
    note: str = ""


# ---------------------------------------------------------------------------
# Monitoring & scheduling (Prompt 38)
# ---------------------------------------------------------------------------
def _enum_value(v):
    return v.value if hasattr(v, "value") else v


class ScheduledJobResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    job_name: str
    job_type: str
    enabled: bool
    interval_seconds: int
    schedule: Optional[str] = None
    timezone: str = "Asia/Kolkata"
    source_id: Optional[str] = None
    current_status: str
    consecutive_failures: int = 0
    max_retries: int = 3
    last_run_at: Optional[datetime] = None
    last_success_at: Optional[datetime] = None
    last_failure_at: Optional[datetime] = None
    next_run_at: Optional[datetime] = None
    last_error: Optional[str] = None

    @field_validator("job_type", "current_status", mode="before")
    @classmethod
    def _ev(cls, v):
        return _enum_value(v)


class ScheduledJobListResponse(BaseModel):
    items: list[ScheduledJobResponse]
    total: int
    scheduler_enabled: bool = False


class SchedulerRunResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    job_name: str
    job_type: str
    source_id: Optional[str] = None
    trigger: str = "SCHEDULE"
    status: str
    started_at: datetime
    finished_at: Optional[datetime] = None
    duration_seconds: Optional[float] = None
    retry_count: int = 0
    records_fetched: int = 0
    records_new: int = 0
    records_changed: int = 0
    records_unchanged: int = 0
    records_removed: int = 0
    signals_changed: int = 0
    opportunities_changed: int = 0
    leads_changed: int = 0
    alerts_generated: int = 0
    error: Optional[str] = None

    @field_validator("job_type", "status", mode="before")
    @classmethod
    def _ev(cls, v):
        return _enum_value(v)


class SchedulerRunListResponse(BaseModel):
    items: list[SchedulerRunResponse]
    total: int


class AlertResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    alert_type: str
    severity: str
    status: str
    title: str
    message: Optional[str] = None
    company_id: Optional[int] = None
    lead_id: Optional[int] = None
    opportunity_id: Optional[int] = None
    signal_id: Optional[int] = None
    tender_id: Optional[int] = None
    source_id: Optional[str] = None
    evidence_ids: list[int] = Field(default_factory=list)
    link: Optional[str] = None
    triggered_at: datetime
    acknowledged_at: Optional[datetime] = None
    resolved_at: Optional[datetime] = None

    @field_validator("alert_type", "severity", "status", mode="before")
    @classmethod
    def _ev(cls, v):
        return _enum_value(v)


class AlertListResponse(BaseModel):
    items: list[AlertResponse]
    total: int
    unread_count: int = 0


class AlertStatusUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    status: str


class NotificationPreferenceResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    hot_leads_only: bool = False
    min_score_increase: int = 10
    enabled_alert_types: list[str] = Field(default_factory=list)
    min_severity: str = "LOW"
    channels: list[str] = Field(default_factory=list)

    @field_validator("min_severity", mode="before")
    @classmethod
    def _ev(cls, v):
        return _enum_value(v)


class NotificationPreferenceUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    hot_leads_only: Optional[bool] = None
    min_score_increase: Optional[int] = None
    enabled_alert_types: Optional[list[str]] = None
    min_severity: Optional[str] = None
    channels: Optional[list[str]] = None


class MonitoringPipelineMetrics(BaseModel):
    raw_records: int = 0
    canonical_jobs: int = 0
    companies: int = 0
    signals: int = 0
    opportunities: int = 0
    leads: int = 0
    tenders: int = 0


class MonitoringSourceMetric(BaseModel):
    source_id: str
    connection_status: str = "NOT_CONFIGURED"
    last_success_at: Optional[datetime] = None
    last_failure_at: Optional[datetime] = None
    last_error: Optional[str] = None
    last_run_at: Optional[datetime] = None
    records_fetched: int = 0


class MonitoringChangeSummary(BaseModel):
    change_type: str
    count: int


class MonitoringDashboardResponse(BaseModel):
    generated_at: datetime
    scheduler_enabled: bool = False
    data_mode: str = "REAL_ONLY"
    pipeline: MonitoringPipelineMetrics
    sources: list[MonitoringSourceMetric] = Field(default_factory=list)
    jobs: list[ScheduledJobResponse] = Field(default_factory=list)
    recent_runs: list[SchedulerRunResponse] = Field(default_factory=list)
    recent_alerts: list[AlertResponse] = Field(default_factory=list)
    unread_alerts: int = 0
    job_change_summary: list[MonitoringChangeSummary] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# CRM & outreach lifecycle (Prompt 39)
# ---------------------------------------------------------------------------
def _ev(v):
    return v.value if hasattr(v, "value") else v


class LeadStatusHistoryResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    lead_id: int
    old_status: Optional[str] = None
    new_status: str
    changed_by: str = "SYSTEM"
    reason: Optional[str] = None
    source: Optional[str] = None
    created_at: datetime


class LeadStatusTransitionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    new_status: str
    reason: Optional[str] = None


class CRMActivityResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    lead_id: Optional[int] = None
    company_id: Optional[int] = None
    contact_id: Optional[int] = None
    opportunity_id: Optional[int] = None
    activity_type: str
    direction: str
    subject: Optional[str] = None
    body_reference: Optional[str] = None
    status: str
    source: Optional[str] = None
    external_id: Optional[str] = None
    is_system_event: bool = False
    occurred_at: datetime
    created_by: str = "SYSTEM"

    @field_validator("activity_type", "direction", "status", mode="before")
    @classmethod
    def _e(cls, v):
        return _ev(v)


class CRMActivityListResponse(BaseModel):
    items: list[CRMActivityResponse]
    total: int


class ActivityCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    activity_type: str = "NOTE"
    lead_id: Optional[int] = None
    company_id: Optional[int] = None
    contact_id: Optional[int] = None
    opportunity_id: Optional[int] = None
    subject: Optional[str] = None
    body_reference: Optional[str] = None


class TimelineItem(BaseModel):
    kind: str                      # SYSTEM_EVENT | HUMAN_ACTIVITY
    category: str
    event_type: str
    title: str
    detail: Optional[str] = None
    occurred_at: datetime
    source: Optional[str] = None


class LeadTimelineResponse(BaseModel):
    lead_id: int
    items: list[TimelineItem]
    total: int


class OutreachDraftResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    lead_id: Optional[int] = None
    company_id: Optional[int] = None
    contact_id: Optional[int] = None
    target_role: Optional[str] = None
    channel: str
    subject: Optional[str] = None
    message: Optional[str] = None
    evidence_ids: list[int] = Field(default_factory=list)
    ai_generated: bool = False
    grounding_ok: bool = True
    confidence: int = 0
    status: str
    recipient_email: Optional[str] = None
    provider: Optional[str] = None
    provider_message_id: Optional[str] = None
    error: Optional[str] = None
    created_by: str = "SYSTEM"
    approved_by: Optional[str] = None
    created_at: datetime
    approved_at: Optional[datetime] = None
    sent_at: Optional[datetime] = None

    @field_validator("channel", "status", mode="before")
    @classmethod
    def _e(cls, v):
        return _ev(v)


class OutreachDraftListResponse(BaseModel):
    items: list[OutreachDraftResponse]
    total: int


class GenerateDraftRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    lead_id: int
    channel: str = "EMAIL"
    contact_id: Optional[int] = None


class DraftEditRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    subject: Optional[str] = None
    message: Optional[str] = None


class FollowUpTaskResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    lead_id: Optional[int] = None
    contact_id: Optional[int] = None
    company_id: Optional[int] = None
    due_at: Optional[datetime] = None
    task_type: str
    title: str
    reason: Optional[str] = None
    status: str
    created_by: str = "SYSTEM"
    created_at: datetime
    completed_at: Optional[datetime] = None

    @field_validator("task_type", "status", mode="before")
    @classmethod
    def _e(cls, v):
        return _ev(v)


class FollowUpTaskListResponse(BaseModel):
    items: list[FollowUpTaskResponse]
    total: int


class FollowUpStatusUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    status: str


class SalesOpportunityResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    company_id: Optional[int] = None
    lead_id: Optional[int] = None
    opportunity_candidate_id: Optional[int] = None
    opportunity_type: Optional[str] = None
    title: str
    description: Optional[str] = None
    estimated_team_scale: Optional[str] = None
    estimated_value: Optional[float] = None
    estimated_value_currency: Optional[str] = None
    value_source: str = "NOT_AVAILABLE"
    confidence: int = 0
    evidence_ids: list[int] = Field(default_factory=list)
    stage: str
    probability: Optional[int] = None
    expected_close_date: Optional[datetime] = None
    owner: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    @field_validator("stage", mode="before")
    @classmethod
    def _e(cls, v):
        return _ev(v)


class SalesOpportunityListResponse(BaseModel):
    items: list[SalesOpportunityResponse]
    total: int


class PipelineStageColumn(BaseModel):
    stage: str
    count: int
    opportunities: list[SalesOpportunityResponse] = Field(default_factory=list)


class PipelineBoardResponse(BaseModel):
    columns: list[PipelineStageColumn]
    total: int


class SalesOpportunityCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: str
    company_id: Optional[int] = None
    lead_id: Optional[int] = None
    opportunity_type: Optional[str] = None
    description: Optional[str] = None
    estimated_team_scale: Optional[str] = None
    estimated_value: Optional[float] = None
    estimated_value_currency: Optional[str] = None
    value_source: str = "NOT_AVAILABLE"


class SalesStageUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    stage: str
    reason: Optional[str] = None


class ConversionMetricResponse(BaseModel):
    label: str
    numerator: int
    denominator: int
    rate: object = None   # float or "INSUFFICIENT_DATA"


class CRMAnalyticsResponse(BaseModel):
    generated_at: datetime
    total_leads: int
    lead_status_counts: dict = Field(default_factory=dict)
    sales_stage_counts: dict = Field(default_factory=dict)
    activity_counts: dict = Field(default_factory=dict)
    real_contacted: int = 0
    real_replies: int = 0
    real_meetings: int = 0
    conversion: list[ConversionMetricResponse] = Field(default_factory=list)
    pipeline_value: object = "NOT_AVAILABLE"
    pipeline_value_currency: Optional[str] = None
    pipeline_value_opportunities: int = 0
    open_opportunities: int = 0
    won: int = 0
    lost: int = 0


class ProviderStatusResponse(BaseModel):
    email_provider: Optional[str] = None
    email_status: str = "NOT_CONFIGURED"
    email_from: Optional[str] = None
    crm_provider: str = "INTERNAL"
    crm_status: str = "CONNECTED"
    webhook_configured: bool = False
    note: str = ""


class WebhookAck(BaseModel):
    received: bool = True
    processed: bool = False
    duplicate: bool = False
    detail: Optional[str] = None


class NextBestActionResponse(BaseModel):
    lead_id: int
    next_best_action: str


class ReadinessResponse(BaseModel):
    status: str                    # ready | not_ready
    checks: dict = Field(default_factory=dict)
