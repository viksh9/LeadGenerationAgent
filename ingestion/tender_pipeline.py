"""Tender ingestion pipeline: raw TENDER records -> structured TenderRecord.

    raw_source_records (record_type=TENDER)
        -> normalize (dates, status, technologies, org, value-only-if-stated)
        -> TenderRecord (idempotent upsert; history preserved)
        -> freshness (verification.freshness) + commercial intent (deterministic)
        -> linked to the BusinessSignal built for the same raw record

Only what the source states is stored; absent values stay NULL/UNKNOWN. Tenders
flow into the existing signal/opportunity engine via business_pipeline (which now
also processes RecordType.TENDER); this module adds the structured tender view.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from database.models import (
    BusinessSignal,
    CommercialIntent,
    DataProvenance,
    RawSourceRecord,
    RecordType,
    TenderRecord,
    TenderStatus,
)
from ingestion.extract import extract_technologies
from intelligence.commercial_intent import IntentInputs, classify_commercial_intent
from verification.freshness import compute_freshness

logger = logging.getLogger("ingestion")

_STATUS_MAP = {
    "open": TenderStatus.OPEN, "live": TenderStatus.OPEN, "active": TenderStatus.OPEN,
    "closing soon": TenderStatus.CLOSING_SOON,
    "closed": TenderStatus.CLOSED, "expired": TenderStatus.CLOSED,
    "cancelled": TenderStatus.CANCELLED, "canceled": TenderStatus.CANCELLED,
    "withdrawn": TenderStatus.CANCELLED, "retendered": TenderStatus.CANCELLED,
    "awarded": TenderStatus.AWARDED, "award": TenderStatus.AWARDED,
}
_CLOSING_SOON_DAYS = 7


@dataclass
class TenderPipelineSummary:
    provenance: str
    input_records: int = 0
    created: int = 0
    updated: int = 0
    errors: list[str] = field(default_factory=list)


def _parse_dt(value: Any) -> Optional[datetime]:
    if isinstance(value, datetime):
        return value.replace(tzinfo=None) if value.tzinfo else value
    if not value or not isinstance(value, str):
        return None
    text = value.strip().replace("Z", "+00:00")
    for parse in (datetime.fromisoformat,):
        try:
            dt = parse(text)
            return dt.replace(tzinfo=None) if dt.tzinfo else dt
        except ValueError:
            continue
    return None


def _derive_status(raw_status: Optional[str], closing_date: Optional[datetime],
                   now: datetime) -> TenderStatus:
    """Status from the source's explicit status, else from the closing date. Never
    inferred OPEN merely because a page is reachable — only from a real future
    closing date."""
    if raw_status:
        mapped = _STATUS_MAP.get(raw_status.strip().lower())
        if mapped is not None:
            return mapped
    if closing_date is not None:
        if closing_date < now:
            return TenderStatus.CLOSED
        if closing_date <= now + timedelta(days=_CLOSING_SOON_DAYS):
            return TenderStatus.CLOSING_SOON
        return TenderStatus.OPEN
    return TenderStatus.UNKNOWN


def normalize_tender(raw: RawSourceRecord, *, now: datetime) -> dict[str, Any]:
    """Build TenderRecord field values from a raw TENDER record (source-only)."""
    payload = raw.raw_payload or {}
    closing_date = _parse_dt(payload.get("closing_date"))
    issue_date = _parse_dt(payload.get("issue_date"))
    award_date = _parse_dt(payload.get("award_date"))
    raw_status = payload.get("status") or payload.get("tender_status")
    status = _derive_status(raw_status, closing_date, now)

    text = " ".join(filter(None, [raw.title, raw.description, payload.get("scope_summary")]))
    technologies = extract_technologies(text)

    # Value only if the source explicitly provides it — never computed.
    est_value = payload.get("estimated_value")
    est_value = float(est_value) if isinstance(est_value, (int, float)) else None

    fresh = compute_freshness(
        signal_type="TENDER", published_at=raw.published_at, observed_at=raw.collected_at,
        closing_date=closing_date, source_status=raw_status, now=now,
    )
    org = payload.get("organization_name") or raw.company_name

    return {
        "source_id": raw.source_id,
        "source_record_id": raw.external_id,
        "content_hash": raw.content_hash,
        "title": raw.title,
        "organization_name": org,
        "signal_origin_organization": org,
        "department": payload.get("department"),
        "organization_type": payload.get("organization_type"),
        "location": raw.location,
        "issue_date": issue_date,
        "publication_date": raw.published_at,
        "closing_date": closing_date,
        "award_date": award_date,
        "estimated_value": est_value,
        "currency": payload.get("currency"),
        "estimated_value_text": payload.get("estimated_value_text"),
        "category": payload.get("category") or raw.industry,
        "technologies": technologies,
        "scope_summary": payload.get("scope_summary") or raw.description,
        "eligibility_summary": payload.get("eligibility_summary"),
        "tender_status": status,
        "source_url": raw.source_url,
        "raw_record_id": raw.id,
        "freshness_score": fresh.score,
        "data_provenance": raw.data_provenance if hasattr(raw, "data_provenance") else DataProvenance.REAL,
    }


def _commercial_intent(fields: dict, *, has_signal: bool) -> CommercialIntent:
    result = classify_commercial_intent(IntentInputs(
        evidence_confidence=fields.get("evidence_confidence", 40),
        is_fresh=fields["freshness_score"] >= 50,
        has_project_or_tender=True,
        has_vendor_or_award=fields["tender_status"] in (TenderStatus.AWARDED,),
        active_it_jobs=0,
        distinct_signal_types=1,
        technology_relevant=bool(fields["technologies"]),
        company_resolved=fields.get("company_id") is not None,
    ))
    return result.intent


def run_tender_pipeline(session: Session, *, provenance: DataProvenance = DataProvenance.REAL,
                        now: Optional[datetime] = None) -> TenderPipelineSummary:
    """Upsert structured TenderRecords from raw TENDER records. Idempotent; history
    preserved (first_seen kept, status/freshness refreshed on re-run)."""
    now = now or datetime.now(timezone.utc).replace(tzinfo=None)
    is_synth = provenance is DataProvenance.SYNTHETIC
    summary = TenderPipelineSummary(provenance=provenance.value)

    stmt = (
        select(RawSourceRecord)
        .where(RawSourceRecord.record_type == RecordType.TENDER)
        .where(RawSourceRecord.is_synthetic.is_(is_synth))
    )
    for raw in session.scalars(stmt):
        summary.input_records += 1
        try:
            fields = normalize_tender(raw, now=now)
            fields["data_provenance"] = provenance
            # Link to the BusinessSignal built for the same raw record (if any).
            signal = session.scalar(
                select(BusinessSignal).where(BusinessSignal.content_hash == raw.content_hash)
            )
            existing = session.scalar(
                select(TenderRecord).where(
                    TenderRecord.source_id == fields["source_id"],
                    TenderRecord.source_record_id == fields["source_record_id"],
                )
            )
            if existing is None:
                tender = TenderRecord(**fields, first_seen_at=now, last_seen_at=now)
                tender.business_signal_id = signal.id if signal else None
                tender.commercial_intent = _commercial_intent(fields, has_signal=bool(signal))
                session.add(tender)
                summary.created += 1
            else:
                # Preserve first_seen + history; refresh mutable state.
                for key in ("tender_status", "closing_date", "award_date", "freshness_score",
                            "technologies", "scope_summary", "title"):
                    setattr(existing, key, fields[key])
                existing.last_seen_at = now
                if signal:
                    existing.business_signal_id = signal.id
                existing.commercial_intent = _commercial_intent(fields, has_signal=bool(signal))
                summary.updated += 1
        except Exception as exc:  # noqa: BLE001 - record per-record, keep going
            summary.errors.append(f"{raw.external_id or raw.id}: {exc}")
            logger.exception("tender_normalize_failed raw_id=%s", raw.id)
    session.commit()
    logger.info("tender_pipeline provenance=%s input=%s created=%s updated=%s",
                provenance.value, summary.input_records, summary.created, summary.updated)
    return summary
