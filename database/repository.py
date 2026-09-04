"""CRUD for the Lead model."""

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from database.models import Lead, utcnow
from database.session import create_session_factory, get_engine, init_db, session_scope

__all__ = [
    "LeadRepository",
    "create_session_factory",
    "get_engine",
    "init_db",
    "session_scope",
]

UPDATABLE_FIELDS = {
    "company_name",
    "industry",
    "location",
    "signal_type",
    "signal_title",
    "signal_description",
    "signal_date",
    "source_name",
    "source_url",
    "technologies",
    "project_name",
    "project_value",
    "estimated_hiring",
    "hiring_roles",
    "company_size",
    "company_website",
    "poc_name",
    "poc_title",
    "poc_linkedin_url",
    "public_contact",
    "signal_confidence",
    "lead_score",
    "lead_priority",
    "opportunity_summary",
    "recommended_action",
    "recommended_pitch",
    "status",
    "last_verified_at",
}


class LeadRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def create_lead(self, **fields: Any) -> Lead:
        company_name = (fields.get("company_name") or "").strip()
        if not company_name:
            raise ValueError("company_name is required")
        payload = {key: value for key, value in fields.items() if key in UPDATABLE_FIELDS}
        payload["company_name"] = company_name
        payload.setdefault("technologies", payload.get("technologies") or [])
        payload.setdefault("hiring_roles", payload.get("hiring_roles") or [])
        now = utcnow()
        payload.setdefault("created_at", now)
        payload.setdefault("updated_at", now)
        lead = Lead(**payload)
        self.session.add(lead)
        self.session.flush()
        return lead

    def get_lead(self, lead_id: int) -> Lead | None:
        return self.session.get(Lead, lead_id)

    def list_leads(
        self,
        *,
        min_score: float = 0.0,
        status: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[Lead]:
        stmt = select(Lead).where(Lead.lead_score >= min_score).order_by(Lead.lead_score.desc())
        if status:
            stmt = stmt.where(Lead.status == status)
        stmt = stmt.offset(offset).limit(limit)
        return list(self.session.scalars(stmt))

    def update_lead(self, lead_id: int, **fields: Any) -> Lead | None:
        lead = self.get_lead(lead_id)
        if lead is None:
            return None
        for key, value in fields.items():
            if key not in UPDATABLE_FIELDS:
                continue
            setattr(lead, key, value)
        lead.updated_at = utcnow()
        self.session.flush()
        return lead

    def delete_lead(self, lead_id: int) -> bool:
        lead = self.get_lead(lead_id)
        if lead is None:
            return False
        self.session.delete(lead)
        self.session.flush()
        return True

    def get_lead_by_company(self, company_name: str) -> Lead | None:
        return self.session.scalar(select(Lead).where(Lead.company_name == company_name))

    def commit(self) -> None:
        self.session.commit()
