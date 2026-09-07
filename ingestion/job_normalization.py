"""JobNormalizationService: raw source record -> NormalizedJob.

Turns a stored RawSourceRecord (a single source's view of a posting) into a
normalized job with structured location, a derived normalized_role (original
title preserved), technologies, a data-quality score, and a source-confidence
score. No deduplication or company aggregation here — those are separate services.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional

from collectors.raw_record import normalize_company_name
from config.collection import DEFAULT_QUALITY_WEIGHTS, DataQualityWeights, source_confidence
from database.models import DataProvenance, JobStatus, RemoteType
from ingestion.extract import extract_technologies, normalize_role
from ingestion.location import normalize_location

_CURRENCY_RE = re.compile(r"\b([A-Z]{3})\b")
_NUM_RE = re.compile(r"\d[\d,]*")
_SENIOR = ("principal", "staff", "lead", "senior", "sr.")
_JUNIOR = ("junior", "jr.", "intern", "trainee", "graduate")


@dataclass
class NormalizedJob:
    source_id: str
    external_id: Optional[str] = None
    source_url: Optional[str] = None
    raw_record_id: Optional[int] = None
    company_name: Optional[str] = None
    normalized_company_name: Optional[str] = None
    company_domain: Optional[str] = None
    original_job_title: Optional[str] = None
    normalized_role: Optional[str] = None
    description: Optional[str] = None
    original_location: Optional[str] = None
    country: Optional[str] = None
    state: Optional[str] = None
    city: Optional[str] = None
    remote_type: RemoteType = RemoteType.UNKNOWN
    employment_type: Optional[str] = None
    experience_level: Optional[str] = None
    salary_min: Optional[float] = None
    salary_max: Optional[float] = None
    currency: Optional[str] = None
    department: Optional[str] = None
    job_category: Optional[str] = None
    technologies: list[str] = field(default_factory=list)
    skills: list[str] = field(default_factory=list)
    published_at: Optional[datetime] = None
    source_updated_at: Optional[datetime] = None
    job_status: JobStatus = JobStatus.UNKNOWN
    data_provenance: DataProvenance = DataProvenance.REAL
    data_quality_score: int = 0
    source_confidence: int = 0
    content_hash: Optional[str] = None
    canonical_key: str = ""


def _naive(dt: Optional[datetime]) -> Optional[datetime]:
    if dt is None:
        return None
    return dt.astimezone(timezone.utc).replace(tzinfo=None) if dt.tzinfo else dt


def _experience_level(title: Optional[str]) -> Optional[str]:
    t = (title or "").lower()
    if any(k in t for k in _SENIOR):
        return "Senior"
    if any(k in t for k in _JUNIOR):
        return "Junior"
    return None


def _salary(raw) -> tuple[Optional[float], Optional[float], Optional[str]]:
    payload = raw.raw_payload or {}
    lo, hi = payload.get("salary_min"), payload.get("salary_max")
    currency = payload.get("salary_currency") or payload.get("currency")
    if lo is not None or hi is not None:
        return (_to_float(lo), _to_float(hi), currency)
    text = raw.salary
    if not text:
        return (None, None, None)
    cur = None
    m = _CURRENCY_RE.search(text)
    if m:
        cur = m.group(1)
    nums = [float(n.replace(",", "")) for n in _NUM_RE.findall(text)]
    if not nums:
        return (None, None, cur)
    return (nums[0], nums[1] if len(nums) > 1 else None, cur)


def _to_float(v: Any) -> Optional[float]:
    try:
        return float(v) if v is not None else None
    except (TypeError, ValueError):
        return None


def _job_status(raw, now: datetime) -> JobStatus:
    payload = raw.raw_payload or {}
    explicit = str(payload.get("job_status") or payload.get("status") or "").lower()
    if explicit in {"closed", "expired", "filled", "inactive"}:
        return JobStatus.EXPIRED
    valid_through = payload.get("valid_through") or payload.get("validThrough")
    if isinstance(valid_through, str):
        try:
            vt = datetime.fromisoformat(valid_through.replace("Z", "+00:00"))
            if _naive(vt) < now:
                return JobStatus.EXPIRED
        except ValueError:
            pass
    return JobStatus.UNKNOWN  # a reachable posting is NOT assumed active


class JobNormalizationService:
    def __init__(self, weights: DataQualityWeights = DEFAULT_QUALITY_WEIGHTS) -> None:
        self.weights = weights

    def _quality(self, job: NormalizedJob) -> int:
        w = self.weights
        present = {
            "company": bool(job.company_name),
            "title": bool(job.original_job_title),
            "published_at": job.published_at is not None,
            "source_url": bool(job.source_url),
            "description": bool(job.description),
            "location": bool(job.city or job.country),
            "technologies": bool(job.technologies),
            "external_id": bool(job.external_id),
        }
        return sum(getattr(w, key) for key, ok in present.items() if ok)

    def normalize(self, raw, *, now: Optional[datetime] = None) -> NormalizedJob:
        now = _naive(now) or datetime.now(timezone.utc).replace(tzinfo=None)
        text = " ".join(p for p in (raw.title, raw.description) if p)
        loc = normalize_location(raw.location)
        payload = raw.raw_payload or {}
        salary_min, salary_max, currency = _salary(raw)
        job = NormalizedJob(
            source_id=raw.source_id,
            external_id=raw.external_id,
            source_url=raw.source_url,
            raw_record_id=getattr(raw, "id", None),
            company_name=raw.company_name,
            normalized_company_name=normalize_company_name(raw.company_name) or None,
            company_domain=raw.company_domain,
            original_job_title=raw.title,
            normalized_role=normalize_role(raw.title),
            description=raw.description,
            original_location=raw.location,
            country=loc.country,
            state=loc.state,
            city=loc.city,
            remote_type=loc.remote_type,
            employment_type=raw.contract_type,
            experience_level=_experience_level(raw.title),
            salary_min=salary_min,
            salary_max=salary_max,
            currency=currency,
            department=payload.get("department"),
            job_category=raw.industry,
            technologies=list(raw.technologies) if raw.technologies else extract_technologies(text),
            skills=list(payload.get("skills") or []),
            published_at=_naive(raw.published_at),
            source_updated_at=_naive(raw.updated_at),
            job_status=_job_status(raw, now),
            data_provenance=DataProvenance.SYNTHETIC if raw.is_synthetic else DataProvenance.REAL,
            content_hash=raw.content_hash,
            source_confidence=source_confidence(raw.source_id),
        )
        job.canonical_key = "|".join([
            job.normalized_company_name or "",
            (job.normalized_role or job.original_job_title or "").strip().lower(),
            (job.city or "").lower(),
        ])
        job.data_quality_score = self._quality(job)
        return job
