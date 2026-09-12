"""Normalized public-intelligence records (secret-free, nothing fabricated).

Providers translate their own responses into these types so the orchestrator and UI
never see provider-specific formats. Every fact carries provenance; a missing email/
phone/LinkedIn stays None — availability is derived only from what a source published.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

# POC status states (§22).
STATUS_VERIFIED = "VERIFIED"
STATUS_LIKELY = "LIKELY"
STATUS_RECOMMENDED_ROLE_ONLY = "RECOMMENDED_ROLE_ONLY"
STATUS_UNVERIFIED = "UNVERIFIED"
STATUS_STALE = "STALE"

# Company-match confidence (§11).
MATCH_VERIFIED = "VERIFIED"
MATCH_LIKELY = "LIKELY"
MATCH_UNKNOWN = "UNKNOWN"

# Source priority (§1/§20): lower rank wins as the canonical field value. Official
# company sources outrank registries/aggregators; OpenCorporates is supporting legal
# evidence and never overrides stronger official-company data.
SOURCE_PRIORITY = {
    "official_company": 1,
    "official_ats": 2,
    "government_registry": 4,
    "opencorporates": 5,
    "github": 6,
    "wikidata": 7,
}


@dataclass
class CompanyContext:
    """Identifiers a provider may use to scope discovery to the target company."""

    company_id: Optional[int]
    company_name: str
    normalized_name: str
    domain: Optional[str] = None
    website: Optional[str] = None
    linkedin_url: Optional[str] = None
    country: Optional[str] = None


@dataclass
class FieldProvenance:
    """Field-level source (§18): which source supplied a specific field value."""

    field: str
    value: Optional[str]
    source: str
    source_url: Optional[str] = None


@dataclass
class PublicPerson:
    """A real person discovered from a public source. Contact fields are only the
    values a source actually published (§6/§7) — never guessed or inferred."""

    full_name: Optional[str] = None
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    job_title: Optional[str] = None
    department: Optional[str] = None
    seniority: Optional[str] = None
    company_name: Optional[str] = None
    company_domain: Optional[str] = None
    linkedin_url: Optional[str] = None
    work_email: Optional[str] = None          # explicitly published business email only
    personal_email: Optional[str] = None
    business_phone: Optional[str] = None       # explicitly published business phone only
    location: Optional[str] = None
    bio: Optional[str] = None
    is_current: Optional[bool] = None
    company_match_status: str = MATCH_UNKNOWN

    # Provenance (mandatory).
    source: str = ""                           # provider name, e.g. official_company
    source_label: str = ""                     # human label, e.g. "Official Company Website"
    source_type: str = ""
    source_url: Optional[str] = None
    source_record_id: Optional[str] = None
    retrieved_at: Optional[datetime] = None
    field_provenance: list[FieldProvenance] = field(default_factory=list)


@dataclass
class PublicContact:
    """A company-level published contact (not attributed to a named person)."""

    kind: str                                  # BUSINESS_EMAIL | COMPANY_PHONE | ...
    value: str
    source: str = ""
    source_label: str = ""
    source_type: str = ""
    source_url: Optional[str] = None


@dataclass
class CompanyFieldEvidenceRecord:
    """Field-level evidence (§18/§19): a single source's support for a company field."""

    field: str
    value: Optional[str]
    source: str                       # human label, e.g. "Official Company Website"
    source_type: str
    source_url: Optional[str] = None
    evidence_text: Optional[str] = None
    source_priority: int = 99
    trust_score: int = 0


@dataclass
class CompanyLocationRecord:
    """A real, source-backed company office/location (§10)."""

    address_line_1: Optional[str] = None
    address_line_2: Optional[str] = None
    city: Optional[str] = None
    state_or_region: Optional[str] = None
    postal_code: Optional[str] = None
    country: Optional[str] = None
    full_address: Optional[str] = None
    location_type: str = "UNKNOWN"
    is_headquarters: bool = False
    source: str = ""
    source_url: Optional[str] = None


@dataclass
class PublicCompanyFacts:
    """Public company identity facts (§3/§14). Only real, sourced values — every
    important field is backed by a CompanyFieldEvidenceRecord."""

    website: Optional[str] = None
    linkedin_url: Optional[str] = None
    github_url: Optional[str] = None      # official GitHub organization URL (evidence-matched)
    country: Optional[str] = None
    industry: Optional[str] = None
    aliases: list[str] = field(default_factory=list)
    wikidata_id: Optional[str] = None
    # Official-company rich facts (§9/§11/§12/§13/§16).
    contact_url: Optional[str] = None
    careers_url: Optional[str] = None
    leadership_url: Optional[str] = None
    company_phone: Optional[str] = None
    company_email: Optional[str] = None
    address_line_1: Optional[str] = None
    address_line_2: Optional[str] = None
    city: Optional[str] = None
    state_or_region: Optional[str] = None
    postal_code: Optional[str] = None
    full_address: Optional[str] = None
    locations: list[CompanyLocationRecord] = field(default_factory=list)
    # OpenCorporates legal-entity facts (§7/§8, Prompt 47). Legal identity is kept
    # DISTINCT from the operating brand/address; a registered address never overwrites
    # the operating address.
    legal_name: Optional[str] = None
    company_number: Optional[str] = None
    jurisdiction_code: Optional[str] = None
    company_status: Optional[str] = None       # ACTIVE / INACTIVE / DISSOLVED / UNKNOWN
    incorporation_date: Optional[str] = None
    registry_url: Optional[str] = None
    opencorporates_url: Optional[str] = None
    opencorporates_id: Optional[str] = None
    india_entity_type: Optional[str] = None    # GLOBAL_COMPANY / INDIA_ENTITY / INDIA_OFFICE / ...
    match_status: Optional[str] = None         # VERIFIED_MATCH / LIKELY_MATCH / MULTIPLE_MATCHES / NO_MATCH
    registered_location: Optional[CompanyLocationRecord] = None
    officers: list[dict] = field(default_factory=list)   # legal officers (name/position/dates) — NOT POCs
    field_evidence: list[CompanyFieldEvidenceRecord] = field(default_factory=list)
    source: str = ""
    source_label: str = ""
    source_url: Optional[str] = None


@dataclass
class ProviderResult:
    """One provider's normalized output for a company."""

    provider: str
    status: str = "OK"                         # OK | EMPTY | UNAVAILABLE | RATE_LIMITED | DISABLED | ERROR
    people: list[PublicPerson] = field(default_factory=list)
    contacts: list[PublicContact] = field(default_factory=list)
    company_facts: Optional[PublicCompanyFacts] = None
    records_found: int = 0
    error: Optional[str] = None
