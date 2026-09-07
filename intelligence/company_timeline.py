"""Company business-event timeline (real events only).

Builds a chronological, de-duplicated timeline for one company from real stored
records — business signals (projects/contracts/expansion/transformation), tenders
(published/closing/awarded), and observed hiring — so distinct-but-related events
can be shown together (§22). Never fabricates events; every entry traces to a real
record with a source URL where available.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from company import repository as repo
from database.models import DataProvenance, TenderRecord


@dataclass
class TimelineEvent:
    date: Optional[datetime]
    category: str            # HIRING | SIGNAL | TENDER
    event_type: str
    title: str
    detail: Optional[str] = None
    source: Optional[str] = None
    source_url: Optional[str] = None

    def as_dict(self) -> dict:
        return {
            "date": self.date.isoformat() if self.date else None,
            "category": self.category, "event_type": self.event_type,
            "title": self.title, "detail": self.detail,
            "source": self.source, "source_url": self.source_url,
        }


def build_company_timeline(
    session: Session, *, normalized_name: str,
    provenance: Optional[DataProvenance] = DataProvenance.REAL,
) -> list[TimelineEvent]:
    events: list[TimelineEvent] = []
    prov = provenance or DataProvenance.REAL

    # Business signals (each is a distinct real event).
    for sig in repo.company_signals(session, normalized_name, prov):
        events.append(TimelineEvent(
            date=sig.published_at or sig.collected_at,
            category="SIGNAL", event_type=sig.signal_type.value,
            title=sig.signal_title or sig.signal_type.value,
            detail=sig.signal_description, source=sig.source_id, source_url=sig.signal_url,
        ))

    # Tenders (published/closing/awarded).
    tenders = session.scalars(
        select(TenderRecord).where(
            TenderRecord.organization_name.is_not(None),
            TenderRecord.data_provenance == prov,
        )
    ).all()
    from collectors.raw_record import normalize_company_name
    for t in tenders:
        if normalize_company_name(t.organization_name or "") != normalized_name:
            continue
        events.append(TimelineEvent(
            date=t.publication_date or t.closing_date or t.first_seen_at,
            category="TENDER", event_type=f"TENDER_{t.tender_status.value}",
            title=t.title or "Tender", detail=t.scope_summary,
            source=t.source_id, source_url=t.source_url,
        ))

    # Hiring — one summarized event from current canonical openings (real counts).
    jobs = repo.company_jobs(session, normalized_name, prov)
    if jobs:
        latest = max((j.published_at for j in jobs if j.published_at), default=None)
        techs: dict[str, int] = {}
        for j in jobs:
            for tech in (j.technologies or []):
                techs[tech] = techs.get(tech, 0) + 1
        top = ", ".join(t for t, _ in sorted(techs.items(), key=lambda kv: -kv[1])[:5])
        events.append(TimelineEvent(
            date=latest, category="HIRING", event_type="OPENINGS_OBSERVED",
            title=f"{len(jobs)} active IT opening(s) observed",
            detail=(f"Top technologies: {top}" if top else None),
        ))

    events.sort(key=lambda e: (e.date is not None, e.date or datetime.min), reverse=True)
    return events
