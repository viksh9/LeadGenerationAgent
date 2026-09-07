"""JobDeduplicationService — group source records into canonical jobs.

Counts each real job once (a canonical JobRecord) while preserving EVERY source
as a JobSourceReference. Uses candidate blocking (by company) before any
expensive comparison, and an explainable layered matcher. MEDIUM-confidence pairs
become JobDuplicateCandidates for human review — never auto-merged.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Iterable, Optional

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from config.collection import source_confidence, source_priority
from config.deduplication import DEDUPLICATION_VERSION, DEFAULT_DEDUP_CONFIG, DedupConfig
from database.models import (
    DataProvenance,
    JobDuplicateCandidate,
    JobRecord,
    JobSourceReference,
    MatchDecision,
)
from processors.deduplication.identity import DedupRecord, MatchResult, match
from processors.normalization.adapters import normalize_raw

logger = logging.getLogger("deduplication")


@dataclass
class _Group:
    records: list[DedupRecord] = field(default_factory=list)

    @property
    def primary(self) -> DedupRecord:
        # Highest priority (lowest number), tie-broken by source confidence.
        return min(self.records, key=lambda r: (r.source_priority, -r.source_confidence))


@dataclass
class DedupSummary:
    provenance: str
    input_records: int = 0
    canonical_jobs: int = 0
    auto_merged: int = 0
    review_candidates: int = 0
    source_references: int = 0
    deduplication_version: str = DEDUPLICATION_VERSION

    @property
    def duplicate_rate(self) -> float:
        if not self.input_records:
            return 0.0
        return round(1 - (self.canonical_jobs / self.input_records), 3)


class JobDeduplicationService:
    def __init__(self, session: Session, config: DedupConfig = DEFAULT_DEDUP_CONFIG) -> None:
        self.session = session
        self.config = config

    # -- record construction ------------------------------------------------ #
    def to_dedup_record(self, raw: Any, *, now: Optional[datetime] = None) -> DedupRecord:
        nj = normalize_raw(raw, now=now)
        get = (lambda k, d=None: raw.get(k, d)) if isinstance(raw, dict) else (lambda k, d=None: getattr(raw, k, d))
        return DedupRecord(
            source_id=get("source_id") or "unknown",
            external_id=get("external_id"),
            source_url=nj.normalized_source_url or get("source_url"),
            content_hash=get("content_hash"),
            normalized_company_name=nj.normalized_company_name,
            original_company_name=nj.original_company_name,
            company_domain=nj.company_domain,
            source_company_id=get("source_company_id"),
            normalized_title=nj.normalized_job_title,
            original_title=nj.original_job_title,
            city=nj.normalized_city, state=nj.normalized_state, country=nj.normalized_country,
            remote_type=nj.remote_type,
            published_at=nj.published_at,
            description=nj.original_description,
            technologies=nj.normalized_technologies,
            roles=[nj.normalized_role] if nj.normalized_role else [],
            salary_min=nj.salary_min, salary_max=nj.salary_max, currency=nj.currency,
            employment_type=nj.employment_type.value,
            job_status=str(get("job_status") or "UNKNOWN"),
            source_priority=source_priority(get("source_id") or ""),
            source_confidence=source_confidence(get("source_id") or ""),
            raw_record_id=get("id"),
            data_provenance=nj.data_provenance,
        )

    # -- matching ----------------------------------------------------------- #
    def calculate_similarity(self, a: DedupRecord, b: DedupRecord) -> MatchResult:
        return match(a, b, self.config)

    def find_match(self, record: DedupRecord, *, provenance: DataProvenance) -> Optional[JobRecord]:
        """Incremental: find an AUTO_MERGE canonical job already in the DB."""
        block = record.blocking_key()
        if not block:
            return None
        stmt = select(JobRecord).where(
            JobRecord.data_provenance == provenance,
            (JobRecord.company_domain == record.company_domain)
            | (JobRecord.normalized_company_name == record.normalized_company_name),
        )
        best: Optional[JobRecord] = None
        best_score = -1
        for jr in self.session.scalars(stmt):
            result = match(record, _job_to_dedup(jr), self.config)
            if result.decision is MatchDecision.AUTO_MERGE and result.score > best_score:
                best, best_score = jr, result.score
        return best

    # -- batch deduplication ------------------------------------------------ #
    def deduplicate(
        self,
        raw_records: Iterable[Any],
        *,
        provenance: DataProvenance = DataProvenance.REAL,
        reset: bool = False,
        persist: bool = True,
        now: Optional[datetime] = None,
    ) -> DedupSummary:
        now = now or datetime.now(timezone.utc).replace(tzinfo=None)
        if reset:
            self.session.execute(delete(JobRecord).where(JobRecord.data_provenance == provenance))
            self.session.execute(delete(JobDuplicateCandidate).where(JobDuplicateCandidate.data_provenance == provenance))
            self.session.commit()

        records = [self.to_dedup_record(r, now=now) for r in raw_records]
        records = [r for r in records if r.data_provenance is provenance and r.normalized_company_name]
        summary = DedupSummary(provenance=provenance.value, input_records=len(records))

        # Deterministic order (stable grouping regardless of input order).
        records.sort(key=lambda r: (r.blocking_key() or "", r.normalized_title or "",
                                    r.city or "", r.source_priority, r.external_id or ""))

        blocks: dict[str, list[_Group]] = {}
        candidates: list[tuple[DedupRecord, DedupRecord, MatchResult]] = []
        for rec in records:
            key = rec.blocking_key()
            groups = blocks.setdefault(key, [])
            auto: Optional[_Group] = None
            auto_score = -1
            review_hits: list[tuple[_Group, MatchResult]] = []
            for g in groups:
                result = match(rec, g.primary, self.config)
                if result.decision is MatchDecision.AUTO_MERGE and result.score > auto_score:
                    auto, auto_score = g, result.score
                elif result.decision is MatchDecision.REVIEW:
                    review_hits.append((g, result))
            if auto is not None:
                auto.records.append(rec)
                summary.auto_merged += 1
            else:
                groups.append(_Group(records=[rec]))
                for g, result in review_hits:
                    candidates.append((rec, g.primary, result))

        # Counts (computed whether or not we persist — supports --dry-run).
        for groups in blocks.values():
            for g in groups:
                summary.canonical_jobs += 1
                summary.source_references += len(g.records)
                if persist:
                    self._persist_group(g, provenance, now)
        summary.review_candidates = len(candidates)
        if persist:
            for a, b, result in candidates:
                self._persist_candidate(a, b, result, provenance, now)
            self.session.commit()
        logger.info(
            "job_dedup provenance=%s input=%s canonical=%s auto_merged=%s review=%s dup_rate=%s",
            provenance.value, summary.input_records, summary.canonical_jobs,
            summary.auto_merged, summary.review_candidates, summary.duplicate_rate,
        )
        return summary

    # -- persistence -------------------------------------------------------- #
    def create_canonical_job(self, group: _Group, provenance: DataProvenance, now: datetime) -> JobRecord:
        return self._persist_group(group, provenance, now)

    def _persist_group(self, group: _Group, provenance: DataProvenance, now: datetime) -> JobRecord:
        primary = group.primary
        sources = {r.source_id for r in group.records}
        job = JobRecord(
            content_hash=primary.content_hash or (primary.normalized_title or ""),
            canonical_key="|".join([primary.normalized_company_name or "",
                                    (primary.normalized_title or "").lower(), (primary.city or "").lower()]),
            company_name=_company_display(group),
            normalized_company_name=primary.normalized_company_name,
            company_domain=primary.company_domain,
            original_job_title=primary.original_title,
            normalized_title=primary.normalized_title,
            normalized_role=(primary.roles[0] if primary.roles else None),
            description=_best_description(group),
            original_location=None,
            city=primary.city, state=primary.state, country=primary.country,
            remote_type=primary.remote_type,
            employment_type=primary.employment_type,
            salary_min=primary.salary_min, salary_max=primary.salary_max, currency=primary.currency,
            technologies=_union_tech(group),
            published_at=primary.published_at,
            job_status=primary.job_status,
            data_provenance=provenance,
            primary_source=primary.source_id,
            source_count=len(sources),
            original_job_titles=sorted({r.original_title for r in group.records if r.original_title}),
            field_conflicts=_field_conflicts(group),
            deduplication_version=DEDUPLICATION_VERSION,
            first_seen_at=now, last_seen_at=now,
        )
        self.session.add(job)
        self.session.flush()
        for rec in group.records:
            job.source_references.append(JobSourceReference(
                source_id=rec.source_id, external_id=rec.external_id, source_url=rec.source_url,
                raw_record_id=rec.raw_record_id, source_confidence=rec.source_confidence,
                source_priority=rec.source_priority, is_primary_source=(rec is primary),
                published_at=rec.published_at, observed_at=now,
            ))
        return job

    def _persist_candidate(self, a: DedupRecord, b: DedupRecord, result: MatchResult,
                           provenance: DataProvenance, now: datetime) -> None:
        self.session.add(JobDuplicateCandidate(
            record_a=_record_snapshot(a), record_b=_record_snapshot(b),
            match_score=result.score, match_confidence=result.confidence,
            matched_fields=result.matched_fields, differences=result.differences,
            reason=result.reason, data_provenance=provenance,
        ))


# --------------------------------------------------------------------------- #
def _company_display(group: _Group) -> Optional[str]:
    # Prefer the longest original company name (usually the most complete).
    names = [r.original_company_name for r in group.records if r.original_company_name]
    if names:
        return max(names, key=len)
    return group.primary.normalized_company_name


def _record_snapshot(r: DedupRecord) -> dict:
    return {"source_id": r.source_id, "external_id": r.external_id, "title": r.original_title,
            "company": r.normalized_company_name, "city": r.city,
            "published_at": r.published_at.isoformat() if r.published_at else None}


def _best_description(group: _Group) -> Optional[str]:
    descs = [r.description for r in group.records if r.description]
    return max(descs, key=len) if descs else None


def _union_tech(group: _Group) -> list[str]:
    seen: list[str] = []
    for r in group.records:
        for t in r.technologies:
            if t not in seen:
                seen.append(t)
    return seen


def _field_conflicts(group: _Group) -> dict:
    conflicts: dict[str, list[dict]] = {}
    salaries = [(r.source_id, r.salary_min, r.salary_max) for r in group.records if r.salary_min or r.salary_max]
    if len({(s[1], s[2]) for s in salaries}) > 1:
        conflicts["salary"] = [{"source": s, "min": lo, "max": hi} for s, lo, hi in salaries]
    dates = [(r.source_id, r.published_at) for r in group.records if r.published_at]
    if len({d[1].date() for d in dates}) > 1:
        conflicts["published_at"] = [{"source": s, "date": d.isoformat()} for s, d in dates]
    statuses = [(r.source_id, r.job_status) for r in group.records if r.job_status]
    if len({s[1] for s in statuses}) > 1:
        conflicts["job_status"] = [{"source": s, "status": st} for s, st in statuses]
    return conflicts


def _job_to_dedup(jr: JobRecord) -> DedupRecord:
    from database.models import RemoteType
    return DedupRecord(
        source_id=jr.primary_source or "unknown",
        normalized_company_name=jr.normalized_company_name, company_domain=jr.company_domain,
        normalized_title=jr.normalized_title or jr.original_job_title, original_title=jr.original_job_title,
        city=jr.city, state=jr.state, country=jr.country,
        remote_type=jr.remote_type if isinstance(jr.remote_type, RemoteType) else RemoteType.UNKNOWN,
        published_at=jr.published_at, description=jr.description, technologies=list(jr.technologies or []),
        source_priority=source_priority(jr.primary_source or ""),
        data_provenance=jr.data_provenance,
    )
