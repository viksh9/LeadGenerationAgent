"""Raw-record helpers: company-name normalization, content hashing, and the
`RawRecordDraft` shape collectors return (pre-persistence).

Parsing/normalization live here, not in the DB model. Hashing is deterministic
over stable fields so the future deduplication engine can detect repeats.
"""

from __future__ import annotations

import hashlib
import re
from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator

# Common legal suffixes stripped during company-name normalization (foundation
# for company-identity resolution — the full algorithm comes later).
_LEGAL_SUFFIXES = (
    "private limited", "pvt ltd", "pvt. ltd.", "pvt", "private", "limited", "ltd",
    "llp", "llc", "inc", "incorporated", "corp", "corporation", "co", "company",
    "gmbh", "plc", "sa", "ag",
)
_PUNCT_RE = re.compile(r"[.,/&()]+")
_WS_RE = re.compile(r"\s+")


def normalize_company_name(name: Optional[str]) -> str:
    """Normalize a company name for identity matching (lowercase, de-suffixed).

    "ABC Technologies Pvt Ltd" and "ABC Technologies" both normalize to
    "abc technologies". Non-destructive: returns "" for empty input.
    """
    if not name:
        return ""
    text = _PUNCT_RE.sub(" ", name.lower())
    text = _WS_RE.sub(" ", text).strip()
    # Repeatedly strip trailing legal suffix tokens.
    changed = True
    while changed:
        changed = False
        for suffix in _LEGAL_SUFFIXES:
            if text == suffix:
                break
            if text.endswith(" " + suffix):
                text = text[: -len(suffix)].strip()
                changed = True
    return text


def _hash_date(value: Optional[datetime]) -> str:
    """Date-only portion of a timestamp (stable across intra-day re-collection)."""
    return value.date().isoformat() if value else ""


def compute_content_hash(
    *,
    source_id: str,
    external_id: Optional[str] = None,
    source_url: Optional[str] = None,
    title: Optional[str] = None,
    company_name: Optional[str] = None,
    published_at: Optional[datetime] = None,
) -> str:
    """Deterministic SHA-256 over stable identity fields (no volatile timestamps)."""
    parts = [
        source_id.strip().lower(),
        (external_id or "").strip().lower(),
        (source_url or "").strip().lower(),
        _WS_RE.sub(" ", (title or "").strip().lower()),
        normalize_company_name(company_name),
        _hash_date(published_at),
    ]
    return hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()


class RawRecordDraft(BaseModel):
    """A raw source record as returned by a collector (before persistence).

    `content_hash` and `normalized_company_name` are auto-derived when not
    supplied. `is_synthetic` is False for real production records.
    """

    model_config = ConfigDict(extra="forbid")

    source_id: str
    external_id: Optional[str] = None
    source_url: Optional[str] = None
    published_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    record_type: str = "OTHER"
    title: Optional[str] = None
    description: Optional[str] = None
    company_name: Optional[str] = None
    normalized_company_name: Optional[str] = None
    company_domain: Optional[str] = None
    source_company_id: Optional[str] = None
    location: Optional[str] = None
    industry: Optional[str] = None
    technologies: list[str] = Field(default_factory=list)
    roles: list[str] = Field(default_factory=list)
    salary: Optional[str] = None
    project_name: Optional[str] = None
    project_value: Optional[float] = None
    contract_type: Optional[str] = None
    raw_payload: dict[str, Any] = Field(default_factory=dict)
    content_hash: Optional[str] = None
    is_synthetic: bool = False

    @model_validator(mode="after")
    def _derive(self) -> "RawRecordDraft":
        if not self.normalized_company_name:
            self.normalized_company_name = normalize_company_name(self.company_name) or None
        if not self.content_hash:
            self.content_hash = compute_content_hash(
                source_id=self.source_id,
                external_id=self.external_id,
                source_url=self.source_url,
                title=self.title,
                company_name=self.company_name,
                published_at=self.published_at,
            )
        return self
