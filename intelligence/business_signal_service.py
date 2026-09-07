"""Business-signal normalization + event deduplication.

Raw NEWS/announcement records -> canonical BusinessSignals. The same real-world
event reported by multiple sources becomes ONE signal (event_group_id) with each
source kept as a SignalSourceReference (PRIMARY / SUPPORTING). Company resolution
is conservative — uncertain company identity is flagged REVIEW.
"""

from __future__ import annotations

import hashlib
import logging
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Iterable, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from collectors.raw_record import normalize_company_name
from config.business_signals import (
    BUSINESS_SOURCE_CONFIDENCE,
    DEFAULT_BUSINESS_SOURCE_CONFIDENCE,
)
from database.models import (
    BusinessSignal,
    BusinessSignalType,
    DataProvenance,
    ResolutionStatus,
    SignalSourceReference,
    SignalStrength,
    SourceRole,
)
from intelligence.business_signal_detector import BusinessSignalDetector, signal_age_days

logger = logging.getLogger("intelligence")


def _source_confidence(source_id: str) -> int:
    return BUSINESS_SOURCE_CONFIDENCE.get(source_id, DEFAULT_BUSINESS_SOURCE_CONFIDENCE)


@dataclass
class NormalizedBusinessSignal:
    source_id: str
    external_id: Optional[str]
    source_url: Optional[str]
    raw_record_id: Optional[int]
    content_hash: str
    event_key: str
    company_name: Optional[str]
    normalized_company_name: Optional[str]
    company_domain: Optional[str]
    resolution_status: ResolutionStatus
    signal_type: BusinessSignalType
    signal_title: Optional[str]
    signal_description: Optional[str]
    signal_url: Optional[str]
    published_at: Optional[datetime]
    signal_age_days: Optional[int]
    project_value: Optional[float]
    currency: Optional[str]
    project_value_text: Optional[str]
    technology_terms: list[str]
    location: Optional[str]
    signal_strength: SignalStrength
    source_confidence: int
    data_quality_score: int
    data_provenance: DataProvenance
    detected_keywords: list[str] = field(default_factory=list)


class BusinessSignalNormalizationService:
    def __init__(self, detector: Optional[BusinessSignalDetector] = None) -> None:
        self.detector = detector or BusinessSignalDetector()

    def normalize(self, raw, *, now: Optional[datetime] = None) -> NormalizedBusinessSignal:
        now = now or datetime.now(timezone.utc).replace(tzinfo=None)
        detected = self.detector.detect(raw.title, raw.description)
        norm_company = normalize_company_name(raw.company_name) or None
        published = raw.published_at
        if published and published.tzinfo:
            published = published.astimezone(timezone.utc).replace(tzinfo=None)

        # Conservative company resolution.
        resolution = ResolutionStatus.RESOLVED if norm_company else ResolutionStatus.REVIEW

        # Event key: same company + signal type + day => same event (cross-source).
        if norm_company:
            day = published.date().isoformat() if published else "nodate"
            event_key = f"{norm_company}|{detected.signal_type.value}|{day}"
        else:
            event_key = f"nocompany|{raw.content_hash}"

        quality = self._quality(raw, detected)
        return NormalizedBusinessSignal(
            source_id=raw.source_id,
            external_id=raw.external_id,
            source_url=raw.source_url,
            raw_record_id=getattr(raw, "id", None),
            content_hash=raw.content_hash,
            event_key=event_key,
            company_name=raw.company_name,
            normalized_company_name=norm_company,
            company_domain=raw.company_domain,
            resolution_status=resolution,
            signal_type=detected.signal_type,
            signal_title=raw.title,
            signal_description=raw.description,
            signal_url=raw.source_url,
            published_at=published,
            signal_age_days=signal_age_days(published, now),
            project_value=detected.project_value,
            currency=detected.currency,
            project_value_text=detected.project_value_text,
            technology_terms=detected.technologies,
            location=raw.location,
            signal_strength=detected.signal_strength,
            source_confidence=_source_confidence(raw.source_id),
            data_quality_score=quality,
            data_provenance=DataProvenance.SYNTHETIC if raw.is_synthetic else DataProvenance.REAL,
            detected_keywords=detected.detected_keywords,
        )

    @staticmethod
    def _quality(raw, detected) -> int:
        score = 0
        score += 20 if raw.company_name else 0
        score += 20 if raw.title else 0
        score += 15 if raw.published_at else 0
        score += 10 if raw.source_url else 0
        score += 10 if raw.description else 0
        score += 15 if detected.technologies else 0
        score += 10 if detected.project_value is not None else 0
        return min(100, score)


def _evidence_confidence(signal: BusinessSignal) -> int:
    """Combine source quality, explicitness, date, company, and corroboration."""
    conf = signal.source_confidence
    if signal.published_at:
        conf += 8
    if signal.normalized_company_name:
        conf += 8
    if signal.project_value is not None:
        conf += 8
    if signal.signal_strength is SignalStrength.STRONG:
        conf += 8
    if signal.source_count > 1:                 # genuine multi-source corroboration
        conf += 6 * min(signal.source_count - 1, 2)
    return max(0, min(100, conf))


class BusinessSignalDeduplicationService:
    """Collapse multi-source reports of the same event into one BusinessSignal."""

    def __init__(self, session: Session) -> None:
        self.session = session

    @dataclass
    class Summary:
        provenance: str
        input: int = 0
        created: int = 0
        supporting_added: int = 0
        duplicates: int = 0
        errors: list[str] = field(default_factory=list)

    def ingest(
        self,
        signals: Iterable[NormalizedBusinessSignal],
        *,
        provenance: DataProvenance = DataProvenance.REAL,
        now: Optional[datetime] = None,
    ) -> "BusinessSignalDeduplicationService.Summary":
        now = now or datetime.now(timezone.utc).replace(tzinfo=None)
        summary = self.Summary(provenance=provenance.value)

        # Preload existing events + content hashes for this provenance.
        by_event: dict[str, BusinessSignal] = {}
        seen_hashes: set[str] = set()
        seen_refs: set[tuple] = set()
        for sig in self.session.scalars(
            select(BusinessSignal).where(BusinessSignal.data_provenance == provenance)
        ):
            by_event[sig.event_group_id or f"h:{sig.content_hash}"] = sig
            seen_hashes.add(sig.content_hash)
            for ref in sig.source_references:
                seen_refs.add((ref.source_id, ref.external_id or None))

        for ns in signals:
            if ns.data_provenance is not provenance:
                continue
            summary.input += 1
            group = _group_id(ns.event_key)
            existing = by_event.get(group)

            if existing is not None:
                # Same event from another source -> supporting evidence.
                key = (ns.source_id, ns.external_id or None)
                if ns.content_hash in seen_hashes or key in seen_refs:
                    summary.duplicates += 1
                    continue
                self._add_ref(existing, ns, now, SourceRole.SUPPORTING)
                existing.source_count = len({r.source_id for r in existing.source_references})
                if ns.source_confidence > existing.source_confidence:
                    existing.source_confidence = ns.source_confidence  # best source wins
                existing.evidence_confidence = _evidence_confidence(existing)
                seen_hashes.add(ns.content_hash)
                seen_refs.add(key)
                summary.supporting_added += 1
                continue

            signal = self._new_signal(ns, now)
            signal.event_group_id = group
            self.session.add(signal)
            self.session.flush()
            self._add_ref(signal, ns, now, SourceRole.PRIMARY)
            signal.source_count = 1
            signal.evidence_confidence = _evidence_confidence(signal)
            by_event[group] = signal
            seen_hashes.add(ns.content_hash)
            seen_refs.add((ns.source_id, ns.external_id or None))
            summary.created += 1

        self.session.commit()
        logger.info(
            "business_signal_dedup provenance=%s input=%s created=%s supporting=%s duplicates=%s",
            provenance.value, summary.input, summary.created, summary.supporting_added, summary.duplicates,
        )
        return summary

    def _new_signal(self, ns: NormalizedBusinessSignal, now: datetime) -> BusinessSignal:
        return BusinessSignal(
            source_id=ns.source_id, external_id=ns.external_id, content_hash=ns.content_hash,
            company_name=ns.company_name, normalized_company_name=ns.normalized_company_name,
            company_domain=ns.company_domain, resolution_status=ns.resolution_status,
            signal_type=ns.signal_type, signal_title=ns.signal_title,
            signal_description=ns.signal_description, signal_url=ns.signal_url,
            published_at=ns.published_at, signal_age_days=ns.signal_age_days,
            project_value=ns.project_value, currency=ns.currency, project_value_text=ns.project_value_text,
            contract_party=None, partner_name=None, technology_terms=list(ns.technology_terms),
            location=ns.location, signal_strength=ns.signal_strength,
            source_confidence=ns.source_confidence, data_quality_score=ns.data_quality_score,
            data_provenance=ns.data_provenance, raw_record_id=ns.raw_record_id,
        )

    @staticmethod
    def _add_ref(signal: BusinessSignal, ns: NormalizedBusinessSignal, now: datetime, role: SourceRole) -> None:
        signal.source_references.append(SignalSourceReference(
            source_id=ns.source_id, source_url=ns.source_url, external_id=ns.external_id,
            published_at=ns.published_at, observed_at=now, source_role=role,
            source_confidence=ns.source_confidence,
        ))


def _group_id(event_key: str) -> str:
    return hashlib.sha256(event_key.encode("utf-8")).hexdigest()[:32]
