"""NormalizedJobRecord — the structured result of normalization.

Holds ORIGINAL source fields AND normalized fields side by side. Per the
architecture (RawSourceRecord -> NormalizedJobRecord -> CanonicalJobRecord), this
is the in-memory normalization stage; the canonical persisted form is JobRecord.
Original fields are never removed.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

from database.models import DataProvenance, RemoteType
from processors.normalization.field_normalizers import EmploymentType, SourceName
from processors.normalization.industry_normalizer import IndustryTaxonomy
from processors.normalization.relevance import ITRelevance
from processors.normalization.role_normalizer import RoleTaxonomy
from processors.normalization.title_normalizer import SeniorityLevel


@dataclass
class NormalizedJobRecord:
    # --- Original source fields (preserved verbatim) ---
    original_job_title: Optional[str] = None
    original_company_name: Optional[str] = None
    original_location: Optional[str] = None
    original_description: Optional[str] = None
    original_source_url: Optional[str] = None
    original_technology_terms: list[str] = field(default_factory=list)
    original_salary_text: Optional[str] = None
    original_date_text: Optional[str] = None
    original_source: Optional[str] = None

    # --- Normalized fields ---
    normalized_job_title: Optional[str] = None
    normalized_role: Optional[str] = None
    role_taxonomy: RoleTaxonomy = RoleTaxonomy.UNKNOWN
    seniority_level: SeniorityLevel = SeniorityLevel.UNKNOWN
    normalized_technologies: list[str] = field(default_factory=list)
    technology_categories: dict[str, str] = field(default_factory=dict)
    normalized_city: Optional[str] = None
    normalized_state: Optional[str] = None
    normalized_country: Optional[str] = None
    normalized_region: Optional[str] = None
    remote_type: RemoteType = RemoteType.UNKNOWN
    normalized_company_name: Optional[str] = None
    company_domain: Optional[str] = None
    company_identity_confidence: int = 0
    industry: IndustryTaxonomy = IndustryTaxonomy.UNKNOWN
    it_relevance: ITRelevance = ITRelevance.UNKNOWN
    employment_type: EmploymentType = EmploymentType.UNKNOWN
    experience_min: Optional[int] = None
    experience_max: Optional[int] = None
    salary_min: Optional[float] = None
    salary_max: Optional[float] = None
    currency: Optional[str] = None
    salary_period: Optional[str] = None
    published_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    normalized_source: SourceName = SourceName.OTHER
    normalized_source_url: Optional[str] = None

    # --- Meta ---
    data_provenance: DataProvenance = DataProvenance.REAL
    normalization_warnings: list[str] = field(default_factory=list)
    normalization_confidence: int = 0
    normalization_version: str = "1.0.0"
