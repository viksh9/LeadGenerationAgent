"""JobDeduplicationService: normalized jobs -> canonical JobRecords + references.

The same opening seen on multiple sources becomes ONE JobRecord with multiple
JobSourceReferences (evidence), never multiple counted openings. Same-source
re-fetches refresh the reference. Real and synthetic are kept separate.
"""

from __future__ import annotations

import logging
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Iterable, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from config.collection import source_priority
from database.models import DataProvenance, JobRecord, JobSourceReference, RemoteType
from ingestion.job_normalization import NormalizedJob

logger = logging.getLogger("ingestion")


@dataclass
class DedupSummary:
    provenance: str
    input_jobs: int = 0
    canonical_created: int = 0
    canonical_updated: int = 0
    duplicates: int = 0
    source_references: int = 0
    errors: list[str] = field(default_factory=list)


class JobDeduplicationService:
    def __init__(self, session: Session) -> None:
        self.session = session

    def _new_record(self, nj: NormalizedJob, now: datetime) -> JobRecord:
        return JobRecord(
            content_hash=nj.content_hash or nj.canonical_key,
            canonical_key=nj.canonical_key,
            company_name=nj.company_name,
            normalized_company_name=nj.normalized_company_name,
            company_domain=nj.company_domain,
            original_job_title=nj.original_job_title,
            normalized_role=nj.normalized_role,
            description=nj.description,
            original_location=nj.original_location,
            country=nj.country,
            state=nj.state,
            city=nj.city,
            remote_type=nj.remote_type,
            employment_type=nj.employment_type,
            experience_level=nj.experience_level,
            salary_min=nj.salary_min,
            salary_max=nj.salary_max,
            currency=nj.currency,
            department=nj.department,
            job_category=nj.job_category,
            technologies=list(nj.technologies),
            skills=list(nj.skills),
            published_at=nj.published_at,
            source_updated_at=nj.source_updated_at,
            job_status=nj.job_status,
            data_provenance=nj.data_provenance,
            data_quality_score=nj.data_quality_score,
            primary_source=nj.source_id,
            source_count=0,
            first_seen_at=now,
            last_seen_at=now,
        )

    def _merge_into(self, record: JobRecord, nj: NormalizedJob, now: datetime) -> bool:
        """Fill gaps on the canonical record from a corroborating source. Returns
        True if the record row changed."""
        changed = False
        # Fill missing content from whatever source has it.
        for attr in ("description", "company_domain", "department", "salary_min", "salary_max", "currency",
                     "experience_level", "published_at"):
            if getattr(record, attr) in (None, "") and getattr(nj, attr) not in (None, ""):
                setattr(record, attr, getattr(nj, attr))
                changed = True
        if record.remote_type is RemoteType.UNKNOWN and nj.remote_type is not RemoteType.UNKNOWN:
            record.remote_type = nj.remote_type
            changed = True
        merged_tech = list(dict.fromkeys([*record.technologies, *nj.technologies]))
        if merged_tech != record.technologies:
            record.technologies = merged_tech
            changed = True
        if nj.data_quality_score > record.data_quality_score:
            record.data_quality_score = nj.data_quality_score
            changed = True
        # Canonical source = highest priority (lowest number) among references.
        if source_priority(nj.source_id) < source_priority(record.primary_source or ""):
            record.primary_source = nj.source_id
            changed = True
        record.last_seen_at = now
        return changed

    def ingest(
        self,
        jobs: Iterable[NormalizedJob],
        *,
        provenance: DataProvenance = DataProvenance.REAL,
        now: Optional[datetime] = None,
    ) -> DedupSummary:
        """Collapse jobs into canonical openings.

        Cross-source dedup pairs postings by ORDINAL within a content key: the
        k-th posting of the same (company, role, city) from any source maps to
        the same canonical opening. So N identical-title requisitions from one
        source stay N distinct openings, while the same N syndicated to a second
        source attach as evidence (source_count += 1) rather than double-counting.
        """
        now = (now or datetime.now(timezone.utc).replace(tzinfo=None))
        if now.tzinfo:
            now = now.astimezone(timezone.utc).replace(tzinfo=None)
        summary = DedupSummary(provenance=provenance.value)

        # Preload existing state (for idempotent re-runs / incremental).
        existing_refs: dict[tuple, JobSourceReference] = {}
        content_seq: dict[str, list[JobRecord]] = defaultdict(list)
        cursor: dict[tuple, int] = defaultdict(int)
        for jr in self.session.scalars(
            select(JobRecord).where(JobRecord.data_provenance == provenance).order_by(JobRecord.id.asc())
        ):
            content_seq[jr.canonical_key].append(jr)
            for ref in jr.source_references:
                existing_refs[(ref.source_id, ref.external_id or None)] = ref
                cursor[(jr.canonical_key, ref.source_id)] += 1

        for nj in jobs:
            if nj.data_provenance is not provenance:
                continue
            if not nj.normalized_company_name:
                summary.errors.append("skipped job with no company")
                continue
            summary.input_jobs += 1
            ckey, src, ext = nj.canonical_key, nj.source_id, (nj.external_id or None)

            # Same exact posting already recorded → refresh observation only.
            if (src, ext) in existing_refs:
                existing_refs[(src, ext)].observed_at = now
                summary.duplicates += 1
                continue

            idx = cursor[(ckey, src)]
            cursor[(ckey, src)] = idx + 1
            seq = content_seq[ckey]
            if idx < len(seq):
                # This source's k-th posting corresponds to an existing opening
                # first seen on another source → confirming evidence, not a new job.
                record = seq[idx]
                self._add_reference(record, nj, now)
                existing_refs[(src, ext)] = record.source_references[-1]
                record.source_count = len({r.source_id for r in record.source_references})
                self._merge_into(record, nj, now)
                summary.duplicates += 1
                summary.canonical_updated += 1
                summary.source_references += 1
            else:
                record = self._new_record(nj, now)
                self.session.add(record)
                self.session.flush()
                self._add_reference(record, nj, now)
                existing_refs[(src, ext)] = record.source_references[-1]
                record.source_count = 1
                seq.append(record)
                summary.canonical_created += 1
                summary.source_references += 1

        self.session.commit()
        logger.info(
            "job_dedup provenance=%s input=%s canonical_created=%s updated=%s duplicates=%s",
            provenance.value, summary.input_jobs, summary.canonical_created,
            summary.canonical_updated, summary.duplicates,
        )
        return summary

    def _add_reference(self, record: JobRecord, nj: NormalizedJob, now: datetime) -> None:
        record.source_references.append(JobSourceReference(
            source_id=nj.source_id,
            external_id=nj.external_id,
            source_url=nj.source_url,
            raw_record_id=nj.raw_record_id,
            source_confidence=nj.source_confidence,
            observed_at=now,
        ))
