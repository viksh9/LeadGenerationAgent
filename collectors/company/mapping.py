"""Map parsed career-page jobs to RawRecordDraft (no scoring/detection here).

Technology and role extraction reuse the existing normalizer logic (backed by
the signal detector's TECHNOLOGY_ALIASES) — not duplicated. Only structured,
non-personal fields are stored; full HTML is never persisted.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Optional
from urllib.parse import urlsplit

from collectors.company.sources import CareerSourceDefinition
from collectors.it_taxonomy import classify_it_relevance
from collectors.raw_record import RawRecordDraft
from ingestion.normalizer import extract_roles, extract_technologies


def _parse_dt(value: Any) -> Optional[datetime]:
    if not value or not isinstance(value, str):
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _external_id(job: dict, url: Optional[str]) -> Optional[str]:
    ident = job.get("identifier")
    if ident:
        return str(ident)
    if url:  # fall back to the URL path as a stable per-source id
        path = urlsplit(url).path.strip("/")
        return path or None
    return None


def job_warnings(job: dict) -> list[str]:
    warnings: list[str] = []
    if not job.get("title"):
        warnings.append("missing job title")
    if not job.get("url"):
        warnings.append("missing job url")
    if job.get("date_posted") and _parse_dt(job.get("date_posted")) is None:
        warnings.append("unparseable date_posted")
    return warnings


def map_job(job: dict, source: CareerSourceDefinition, *, method: str = "generic") -> RawRecordDraft:
    """Map one parsed job dict to a RawRecordDraft (is_synthetic = False)."""
    title = job.get("title")
    description = job.get("description")
    text = " ".join(p for p in (title, description) if p)
    company_name = job.get("company") or source.company_name
    company_domain = job.get("company_domain") or source.company_domain
    url = job.get("url") or source.career_url
    relevance = classify_it_relevance(title, description, job.get("department"))

    # Structured, non-personal payload only (§27, §28, §29). No raw HTML.
    payload = {
        "source": "company-career-page",
        "source_id": source.source_id,
        "collection_method": method,
        "job_url": url,
        "title": title,
        "date_posted": job.get("date_posted"),
        "valid_through": job.get("valid_through"),
        "employment_type": job.get("employment_type"),
        "department": job.get("department"),
        "location": job.get("location"),
        "city": job.get("city"),
        "state": job.get("state"),
        "country": job.get("country") or source.country,
        "remote": job.get("remote"),
        "company": company_name,
        "company_domain": company_domain,
        "it_relevance": relevance,
        "requires_js": source.requires_js,
    }

    return RawRecordDraft(
        source_id=source.source_id,
        external_id=_external_id(job, url),
        source_url=url,
        published_at=_parse_dt(job.get("date_posted")),
        record_type="JOB_POSTING",
        title=title,
        description=description,
        company_name=company_name,
        company_domain=company_domain,
        location=job.get("location"),
        industry=source.industry,
        technologies=extract_technologies(text),
        roles=extract_roles(text),
        salary=job.get("salary"),
        contract_type=job.get("employment_type"),
        raw_payload=payload,
        is_synthetic=False,
    )
