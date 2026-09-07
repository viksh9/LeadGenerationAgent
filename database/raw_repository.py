"""Repository for the internal raw-source ingestion layer.

Internal only — there is no public CRUD API for raw records. Normalization,
deduplication and scoring consume these; they do not run here.
"""

from __future__ import annotations

from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from collectors.raw_record import RawRecordDraft
from database.models import RawSourceRecord, RecordType

_ALLOWED_FIELDS = {c.name for c in RawSourceRecord.__table__.columns} - {"id"}


def _coerce_record_type(value: object) -> RecordType:
    if isinstance(value, RecordType):
        return value
    try:
        return RecordType(str(value))
    except ValueError:
        return RecordType.OTHER


def create_raw_record(session: Session, **fields: object) -> RawSourceRecord:
    """Insert a raw record from explicit fields (unknown keys ignored)."""
    data = {k: v for k, v in fields.items() if k in _ALLOWED_FIELDS}
    if "record_type" in data:
        data["record_type"] = _coerce_record_type(data["record_type"])
    record = RawSourceRecord(**data)
    session.add(record)
    session.commit()
    session.refresh(record)
    return record


def create_raw_record_from_draft(session: Session, draft: RawRecordDraft) -> RawSourceRecord:
    """Insert a raw record from a collector's `RawRecordDraft`."""
    return create_raw_record(session, **draft.model_dump())


def get_raw_record(session: Session, record_id: int) -> Optional[RawSourceRecord]:
    return session.get(RawSourceRecord, record_id)


def list_raw_records(
    session: Session,
    *,
    source_id: Optional[str] = None,
    limit: int = 100,
    offset: int = 0,
) -> list[RawSourceRecord]:
    stmt = select(RawSourceRecord)
    if source_id is not None:
        stmt = stmt.where(RawSourceRecord.source_id == source_id)
    stmt = stmt.order_by(RawSourceRecord.collected_at.desc()).limit(limit).offset(offset)
    return list(session.scalars(stmt).all())


def find_by_external_id(
    session: Session, source_id: str, external_id: str
) -> Optional[RawSourceRecord]:
    stmt = select(RawSourceRecord).where(
        RawSourceRecord.source_id == source_id,
        RawSourceRecord.external_id == external_id,
    )
    return session.scalars(stmt).first()


def find_by_content_hash(session: Session, content_hash: str) -> Optional[RawSourceRecord]:
    stmt = select(RawSourceRecord).where(RawSourceRecord.content_hash == content_hash)
    return session.scalars(stmt).first()
