"""Normalize a RawSourceRecord into a LeadAnalyzeRequest.

Reuses the canonical technology aliases from the signal detector (no duplicated
data). Role and hiring-count extraction are normalization concerns (turning free
text into structured fields); final signal/opportunity/score classification still
happens in the intelligence engines downstream.
"""

from __future__ import annotations

from typing import Optional

from pydantic import ValidationError

from api.schemas import LeadAnalyzeRequest
from database.models import RawSourceRecord

# Friendly source labels (fallback: title-cased source_id).
SOURCE_LABELS: dict[str, str] = {
    "adzuna": "Adzuna",
    "company_career_pages": "Company Career Page",
    "government_open_data": "Government Open Data",
    "rss_news": "Business News",
    "project_registry": "Project Registry",
    "business_database": "Business Database",
}

# Text-extraction helpers live in ingestion.extract (dependency-light so the
# aggregator/collectors can reuse them without importing the API package).
# Re-exported here to preserve the existing import surface.
from ingestion.extract import (  # noqa: E402,F401
    ROLE_ALIASES,
    extract_estimated_hiring,
    extract_roles,
    extract_technologies,
)


def source_label(source_id: str) -> str:
    return SOURCE_LABELS.get(source_id, source_id.replace("_", " ").title())


def normalize_raw_record(raw: RawSourceRecord) -> Optional[LeadAnalyzeRequest]:
    """Build a validated LeadAnalyzeRequest from a raw record.

    Returns None when the record cannot become a lead (e.g. missing company name
    or no usable signal text) or fails request validation.
    """
    company = (raw.company_name or "").strip()
    text = f"{raw.title or ''}. {raw.description or ''}".strip(". ").strip()
    if not company or not text:
        return None

    technologies = extract_technologies(text)
    # Preserve any technologies already on the raw record.
    for tech in raw.technologies or []:
        if tech not in technologies:
            technologies.append(tech)

    try:
        return LeadAnalyzeRequest(
            company_name=company,
            industry=raw.industry,
            location=raw.location,
            signal_title=raw.title,
            signal_description=raw.description or raw.title,
            signal_date=raw.published_at,
            source_name=source_label(raw.source_id),
            source_url=raw.source_url,
            technologies=technologies,
            hiring_roles=extract_roles(text),
            estimated_hiring=extract_estimated_hiring(text),
            project_name=raw.project_name,
            project_value=raw.project_value,
        )
    except ValidationError:
        return None
