"""Follow-up tasks (§16, §17).

Tasks are created from REAL lead state only — never invented busy-work. The
scheduler-facing ``generate_from_conditions`` derives tasks from real conditions:
a confirmed send with no reply after an interval, a real tender closing soon, and
a real lead-priority increase. It NEVER sends anything (§17) — it only creates
review/reminder tasks for a human. All tasks are deduplicated by ``dedup_key``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from config.exceptions import NotFoundError, ValidationError
from database.models import (
    CRMActivity,
    ActivityType,
    DataProvenance,
    FollowUpStatus,
    FollowUpTask,
    FollowUpType,
    LeadChangeEvent,
    OutreachDraft,
    OutreachDraftStatus,
    TenderRecord,
    TenderStatus,
    utcnow,
)

DEFAULT_NO_REPLY_SECONDS = 3 * 24 * 3600      # follow up 3 days after a send with no reply
DEFAULT_TENDER_WINDOW_DAYS = 7


class FollowUpService:
    def __init__(self, session: Session):
        self.session = session

    def create(self, *, title: str, task_type: FollowUpType = FollowUpType.OTHER,
               lead_id: int | None = None, contact_id: int | None = None, company_id: int | None = None,
               due_at: datetime | None = None, reason: str | None = None,
               dedup_key: str | None = None, created_by: str = "human",
               now: datetime | None = None) -> FollowUpTask | None:
        now = now or utcnow()
        if dedup_key and self._exists(dedup_key):
            return None
        task = FollowUpTask(
            title=title[:255], task_type=task_type, lead_id=lead_id, contact_id=contact_id,
            company_id=company_id, due_at=due_at, reason=reason, dedup_key=dedup_key,
            status=FollowUpStatus.OPEN, created_by=created_by, created_at=now,
        )
        self.session.add(task)
        self.session.flush()
        return task

    def _exists(self, dedup_key: str) -> bool:
        return self.session.execute(
            select(FollowUpTask.id).where(FollowUpTask.dedup_key == dedup_key)
        ).scalars().first() is not None

    def list(self, *, status: FollowUpStatus | None = None, lead_id: int | None = None,
             limit: int = 100) -> list[FollowUpTask]:
        stmt = select(FollowUpTask)
        if status is not None:
            stmt = stmt.where(FollowUpTask.status == status)
        if lead_id is not None:
            stmt = stmt.where(FollowUpTask.lead_id == lead_id)
        stmt = stmt.order_by(FollowUpTask.due_at.asc().nullslast(), FollowUpTask.id.desc()).limit(limit)
        return list(self.session.execute(stmt).scalars().all())

    def set_status(self, task_id: int, status: FollowUpStatus, *, now: datetime | None = None) -> FollowUpTask:
        now = now or utcnow()
        task = self.session.get(FollowUpTask, task_id)
        if task is None:
            raise NotFoundError(f"Follow-up task {task_id} not found.")
        task.status = status
        if status is FollowUpStatus.COMPLETED:
            task.completed_at = now
        self.session.flush()
        return task

    # ------------------------------------------------------------------ #
    # Scheduler-facing generation from REAL conditions (§17)
    # ------------------------------------------------------------------ #
    def generate_from_conditions(
        self, *, now: datetime | None = None,
        no_reply_seconds: int = DEFAULT_NO_REPLY_SECONDS,
        tender_window_days: int = DEFAULT_TENDER_WINDOW_DAYS,
        run_since: datetime | None = None,
    ) -> int:
        now = now or utcnow()
        created = 0
        created += self._followup_on_no_reply(now, no_reply_seconds)
        created += self._followup_on_tender_deadline(now, tender_window_days)
        created += self._review_on_priority_increase(now, run_since)
        self.session.flush()
        return created

    def _followup_on_no_reply(self, now: datetime, no_reply_seconds: int) -> int:
        cutoff = now - timedelta(seconds=no_reply_seconds)
        sent = self.session.execute(
            select(OutreachDraft).where(
                OutreachDraft.status == OutreachDraftStatus.SENT,
                OutreachDraft.sent_at.is_not(None),
                OutreachDraft.sent_at <= cutoff,
            )
        ).scalars().all()
        created = 0
        for draft in sent:
            # Real reply after the send? Then no follow-up needed.
            replied = self.session.execute(
                select(CRMActivity.id).where(
                    CRMActivity.lead_id == draft.lead_id,
                    CRMActivity.activity_type == ActivityType.EMAIL_REPLY,
                    CRMActivity.occurred_at >= draft.sent_at,
                )
            ).scalars().first()
            if replied:
                continue
            task = self.create(
                title="Follow up — no reply after outreach",
                task_type=FollowUpType.FOLLOW_UP, lead_id=draft.lead_id, company_id=draft.company_id,
                contact_id=draft.contact_id, due_at=now, reason="Sent email received no reply in the window.",
                dedup_key=f"noreply:draft:{draft.id}", created_by="SYSTEM", now=now,
            )
            created += 1 if task else 0
        return created

    def _followup_on_tender_deadline(self, now: datetime, window_days: int) -> int:
        horizon = now + timedelta(days=window_days)
        tenders = self.session.execute(
            select(TenderRecord).where(
                TenderRecord.data_provenance == DataProvenance.REAL,
                TenderRecord.closing_date.is_not(None),
                TenderRecord.closing_date >= now,
                TenderRecord.closing_date <= horizon,
                TenderRecord.tender_status.in_([TenderStatus.OPEN, TenderStatus.CLOSING_SOON,
                                                TenderStatus.UNKNOWN]),
            )
        ).scalars().all()
        created = 0
        for t in tenders:
            task = self.create(
                title=f"Check tender deadline: {(t.title or t.organization_name or 'tender')[:80]}",
                task_type=FollowUpType.CHECK_TENDER_DEADLINE, company_id=t.company_id or t.target_company_id,
                due_at=t.closing_date, reason=f"Closes {t.closing_date.date().isoformat()}.",
                dedup_key=f"tender:{t.id}:{t.closing_date.date().isoformat()}", created_by="SYSTEM", now=now,
            )
            created += 1 if task else 0
        return created

    def _review_on_priority_increase(self, now: datetime, run_since: datetime | None) -> int:
        if run_since is None:
            return 0
        events = self.session.execute(
            select(LeadChangeEvent).where(
                LeadChangeEvent.change_type == "PRIORITY_CHANGED",
                LeadChangeEvent.detected_at >= run_since,
            )
        ).scalars().all()
        created = 0
        for ev in events:
            task = self.create(
                title="Review lead — priority increased",
                task_type=FollowUpType.REVIEW_LEAD, lead_id=ev.lead_id, company_id=ev.company_id,
                due_at=now, reason=f"Priority {ev.old_value} → {ev.new_value}.",
                dedup_key=f"priority:lead:{ev.lead_id}:{ev.new_value}", created_by="SYSTEM", now=now,
            )
            created += 1 if task else 0
        return created
