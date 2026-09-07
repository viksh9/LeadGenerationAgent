"""Normalize a RawSourceRecord into a LeadAnalyzeRequest.

Reuses the canonical technology aliases from the signal detector (no duplicated
data). Role and hiring-count extraction are normalization concerns (turning free
text into structured fields); final signal/opportunity/score classification still
happens in the intelligence engines downstream.
"""

from __future__ import annotations

import re
from typing import Optional

from pydantic import ValidationError

from api.schemas import LeadAnalyzeRequest
from database.models import RawSourceRecord
from intelligence.signal_detector import TECHNOLOGY_ALIASES

# Friendly source labels (fallback: title-cased source_id).
SOURCE_LABELS: dict[str, str] = {
    "adzuna": "Adzuna",
    "company_career_pages": "Company Career Page",
    "government_open_data": "Government Open Data",
    "rss_news": "Business News",
    "project_registry": "Project Registry",
    "business_database": "Business Database",
}

# Common IT hiring roles (canonical -> match aliases). Normalization only.
ROLE_ALIASES: dict[str, tuple[str, ...]] = {
    "Java Engineer": ("java engineer", "java developer"),
    "Backend Engineer": ("backend engineer", "back-end engineer", "backend developer"),
    "Frontend Engineer": ("frontend engineer", "front-end engineer", "frontend developer"),
    "React Developer": ("react developer", "react engineer"),
    "Python Developer": ("python developer", "python engineer"),
    "AWS Engineer": ("aws engineer",),
    "Cloud Engineer": ("cloud engineer",),
    "DevOps Engineer": ("devops engineer",),
    "QA Automation Engineer": ("qa automation engineer", "automation engineer", "qa engineer"),
    "SDET": ("sdet",),
    "Data Engineer": ("data engineer",),
    "ML Engineer": ("ml engineer", "machine learning engineer"),
    "Platform Engineer": ("platform engineer",),
    "Full Stack Engineer": ("full stack engineer", "fullstack engineer", "full-stack engineer"),
    "Software Engineer": ("software engineer", "software developer"),
}

_HIRING_NOUNS = r"(?:engineers|developers|professionals|specialists|hires|openings|positions|roles)"
# A count near a hiring noun ("30 Java, AWS engineers") or an explicit "hiring 30".
_HIRING_RE = re.compile(
    rf"(?:\bhiring\s+(\d{{1,4}})\b)|(\d{{1,4}})\s*\+?[\w,./&+\s-]{{0,40}}?{_HIRING_NOUNS}",
    re.IGNORECASE,
)


def _match_aliases(text: str, aliases: dict[str, tuple[str, ...]], *, allow_plural: bool = False) -> list[str]:
    lowered = text.lower()
    suffix = "s?" if allow_plural else ""
    found: list[str] = []
    for canonical, variants in aliases.items():
        for variant in variants:
            if re.search(rf"(?<![\w]){re.escape(variant)}{suffix}(?![\w])", lowered):
                found.append(canonical)
                break
    return found


def extract_technologies(text: str) -> list[str]:
    """Canonical technologies mentioned in `text` (reuses TECHNOLOGY_ALIASES)."""
    return _match_aliases(text, TECHNOLOGY_ALIASES)


def extract_roles(text: str) -> list[str]:
    """Canonical IT hiring roles mentioned in `text` (singular or plural)."""
    return _match_aliases(text, ROLE_ALIASES, allow_plural=True)


def extract_estimated_hiring(text: str) -> Optional[int]:
    """Largest explicit hiring count mentioned in `text` (or None)."""
    counts = [int(g) for match in _HIRING_RE.findall(text or "") for g in match if g]
    return max(counts) if counts else None


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
