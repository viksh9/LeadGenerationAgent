"""Map Adzuna job records to RawRecordDraft, plus IT relevance + quality checks.

Mapping only — no signal detection or scoring. Missing fields are tolerated and
flagged as warnings; borderline records are kept (only obvious non-IT is filtered).
"""

from __future__ import annotations

import re
from datetime import datetime
from typing import Any, Optional

from collectors.jobs.config import IT_RELEVANCE_TERMS
from collectors.raw_record import RawRecordDraft

SOURCE_ID = "adzuna"

# Single alphanumeric tokens (e.g. "ai", "ml", "java") are matched on word
# boundaries so short terms don't false-positive inside unrelated words
# ("ai" in "waiter"). Compound/special-char terms (".net", "full stack") fall
# back to substring matching. Filter stays lenient — over-keeping is the safe way.
_WORD_TERMS = tuple(t for t in IT_RELEVANCE_TERMS if t.isalnum() and " " not in t)
_SUBSTRING_TERMS = tuple(t for t in IT_RELEVANCE_TERMS if t not in _WORD_TERMS)
_WORD_RE = re.compile(r"\b(?:" + "|".join(re.escape(t) for t in _WORD_TERMS) + r")\b")


def _parse_dt(value: Any) -> Optional[datetime]:
    if not value or not isinstance(value, str):
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _salary(item: dict[str, Any]) -> Optional[str]:
    lo, hi = item.get("salary_min"), item.get("salary_max")
    if lo is None and hi is None:
        return None
    predicted = " (predicted)" if item.get("salary_is_predicted") in (1, "1", True) else ""
    return f"{int(lo) if lo is not None else '?'}-{int(hi) if hi is not None else '?'}{predicted}"


def is_it_relevant(item: dict[str, Any]) -> bool:
    """Lenient IT relevance check (keeps borderline records; drops obvious non-IT)."""
    haystack = " ".join(
        str(x)
        for x in (
            item.get("title", ""),
            item.get("description", ""),
            (item.get("category") or {}).get("label", ""),
            (item.get("category") or {}).get("tag", ""),
        )
    ).lower()
    if _WORD_RE.search(haystack):
        return True
    return any(term in haystack for term in _SUBSTRING_TERMS)


def job_warnings(item: dict[str, Any]) -> list[str]:
    """Data-quality warnings — never silently discard malformed records (§39)."""
    warnings: list[str] = []
    if item.get("id") is None:
        warnings.append("missing job id")
    if not item.get("title"):
        warnings.append("missing title")
    if not (item.get("company") or {}).get("display_name"):
        warnings.append("missing company name")
    if not item.get("redirect_url"):
        warnings.append("missing source url")
    if item.get("created") and _parse_dt(item.get("created")) is None:
        warnings.append("unparseable created date")
    return warnings


def map_job(
    item: dict[str, Any],
    *,
    country: str,
    query: Optional[str] = None,
    location: Optional[str] = None,
) -> RawRecordDraft:
    """Map one Adzuna job record to a RawRecordDraft (is_synthetic = False)."""
    company = (item.get("company") or {}).get("display_name")
    display_location = (item.get("location") or {}).get("display_name")
    category = item.get("category") or {}
    contract = item.get("contract_type") or item.get("contract_time")

    # Preserve collection context alongside the original payload (no credentials).
    payload = dict(item)
    payload["_collection"] = {"country": country, "query": query, "searched_location": location}

    return RawRecordDraft(
        source_id=SOURCE_ID,
        external_id=str(item["id"]) if item.get("id") is not None else None,
        source_url=item.get("redirect_url"),
        published_at=_parse_dt(item.get("created")),
        record_type="JOB_POSTING",
        title=item.get("title"),
        description=item.get("description"),
        company_name=company,
        location=display_location,
        industry=category.get("label"),
        salary=_salary(item),
        contract_type=contract,
        raw_payload=payload,
        is_synthetic=False,
    )
