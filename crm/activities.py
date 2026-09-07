"""CRM activity service (§4, §36).

An activity is a REAL event: a human note/call/meeting, a system event, or a
provider-confirmed send/reply. ``status`` is only ``SENT`` when a real provider
confirms it and only ``REPLIED``/``COMPLETED`` when a real event is recorded —
this service never fabricates activity. Activities are deduplicated by
(source, external_id) so provider re-delivery cannot create duplicates.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from database.models import (
    ActivityDirection,
    ActivityStatus,
    ActivityType,
    CRMActivity,
    DataProvenance,
    utcnow,
)


class CRMActivityService:
    def __init__(self, session: Session):
        self.session = session

    def log(
        self,
        *,
        activity_type: ActivityType,
        lead_id: int | None = None,
        company_id: int | None = None,
        contact_id: int | None = None,
        opportunity_id: int | None = None,
        direction: ActivityDirection = ActivityDirection.INTERNAL,
        status: ActivityStatus = ActivityStatus.COMPLETED,
        subject: str | None = None,
        body_reference: str | None = None,
        source: str | None = "INTERNAL",
        external_id: str | None = None,
        is_system_event: bool = False,
        created_by: str = "SYSTEM",
        occurred_at: datetime | None = None,
        now: datetime | None = None,
    ) -> CRMActivity:
        """Create an activity. If (source, external_id) already exists, the
        existing row is returned unchanged (idempotent for provider events)."""
        now = now or utcnow()
        if source and external_id:
            existing = self.session.execute(
                select(CRMActivity).where(
                    CRMActivity.source == source, CRMActivity.external_id == external_id
                )
            ).scalars().first()
            if existing is not None:
                return existing

        activity = CRMActivity(
            lead_id=lead_id, company_id=company_id, contact_id=contact_id,
            opportunity_id=opportunity_id, activity_type=activity_type, direction=direction,
            status=status, subject=(subject or None) and subject[:512], body_reference=body_reference,
            source=source, external_id=external_id, is_system_event=is_system_event,
            occurred_at=occurred_at or now, created_by=created_by, data_provenance=DataProvenance.REAL,
        )
        self.session.add(activity)
        self.session.flush()
        return activity

    def list_for_lead(self, lead_id: int, *, limit: int = 100) -> list[CRMActivity]:
        return list(self.session.execute(
            select(CRMActivity).where(CRMActivity.lead_id == lead_id)
            .order_by(CRMActivity.occurred_at.desc(), CRMActivity.id.desc()).limit(limit)
        ).scalars().all())

    def list_for_company(self, company_id: int, *, limit: int = 100) -> list[CRMActivity]:
        return list(self.session.execute(
            select(CRMActivity).where(CRMActivity.company_id == company_id)
            .order_by(CRMActivity.occurred_at.desc(), CRMActivity.id.desc()).limit(limit)
        ).scalars().all())

    def latest_for_lead(self, lead_id: int) -> CRMActivity | None:
        return self.session.execute(
            select(CRMActivity).where(CRMActivity.lead_id == lead_id)
            .order_by(CRMActivity.occurred_at.desc(), CRMActivity.id.desc()).limit(1)
        ).scalars().first()
