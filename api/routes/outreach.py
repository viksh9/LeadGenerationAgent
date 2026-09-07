"""Outreach endpoints (§5, §11, §30, §38).

Drafts are generated grounded in real evidence. Sending is explicit, human-gated,
rate-limited, and only ever marks SENT on a real provider confirmation. There is
no bulk/auto send. Read endpoints allow any role; generate/approve/send require
SALES (or ADMIN). Provider status never exposes secrets.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from api.dependencies import get_session
from api.schemas import (
    DraftEditRequest,
    GenerateDraftRequest,
    OutreachDraftListResponse,
    OutreachDraftResponse,
    ProviderStatusResponse,
)
from api.security import rate_limit, require_role
from config import get_settings
from config.exceptions import ValidationError
from crm.providers.crm_provider import crm_provider_status
from crm.providers.email_provider import email_provider_status
from database.models import OutreachChannel, OutreachDraft, OutreachDraftStatus, UserRole
from outreach.send import send_draft
from outreach.service import OutreachService

router = APIRouter(prefix="/outreach", tags=["outreach"])

_sales = require_role(UserRole.SALES)
_viewer = require_role(UserRole.VIEWER, UserRole.RESEARCHER, UserRole.SALES)
_send_limit = rate_limit("outreach_send", 30)   # at most 30 sends/min process-wide


@router.get("/drafts", response_model=OutreachDraftListResponse, summary="List outreach drafts")
def list_drafts(status: str | None = None, limit: int = Query(100, le=500), offset: int = 0,
                session: Session = Depends(get_session), role=Depends(_viewer)) -> OutreachDraftListResponse:
    stmt = select(OutreachDraft)
    if status:
        try:
            stmt = stmt.where(OutreachDraft.status == OutreachDraftStatus(status.upper()))
        except ValueError as exc:
            raise ValidationError(f"Invalid draft status '{status}'.") from exc
    stmt = stmt.order_by(OutreachDraft.updated_at.desc()).limit(limit).offset(offset)
    rows = session.execute(stmt).scalars().all()
    total = int(session.execute(select(func.count(OutreachDraft.id))).scalar() or 0)
    return OutreachDraftListResponse(items=[OutreachDraftResponse.model_validate(r) for r in rows],
                                     total=total)


@router.get("/drafts/{draft_id}", response_model=OutreachDraftResponse, summary="Get a draft")
def get_draft(draft_id: int, session: Session = Depends(get_session),
              role=Depends(_viewer)) -> OutreachDraftResponse:
    draft = OutreachService(session).get(draft_id)
    if draft is None:
        from config.exceptions import NotFoundError
        raise NotFoundError(f"Outreach draft {draft_id} not found.")
    return OutreachDraftResponse.model_validate(draft)


@router.post("/drafts", response_model=OutreachDraftResponse, summary="Generate an evidence-grounded draft")
def generate_draft(payload: GenerateDraftRequest, session: Session = Depends(get_session),
                   role=Depends(_sales)) -> OutreachDraftResponse:
    try:
        channel = OutreachChannel(payload.channel.upper())
    except ValueError as exc:
        raise ValidationError(f"Invalid channel '{payload.channel}'.") from exc
    draft = OutreachService(session).generate_draft(payload.lead_id, channel=channel,
                                                    contact_id=payload.contact_id, actor="human")
    session.commit()
    return OutreachDraftResponse.model_validate(draft)


@router.put("/drafts/{draft_id}", response_model=OutreachDraftResponse, summary="Edit a draft")
def edit_draft(draft_id: int, payload: DraftEditRequest, session: Session = Depends(get_session),
               role=Depends(_sales)) -> OutreachDraftResponse:
    draft = OutreachService(session).update_content(draft_id, subject=payload.subject,
                                                    message=payload.message, actor="human")
    session.commit()
    return OutreachDraftResponse.model_validate(draft)


@router.post("/drafts/{draft_id}/approve", response_model=OutreachDraftResponse,
             summary="Human approval (required before sending)")
def approve_draft(draft_id: int, session: Session = Depends(get_session),
                  role=Depends(_sales)) -> OutreachDraftResponse:
    draft = OutreachService(session).approve(draft_id, approved_by="human")
    session.commit()
    return OutreachDraftResponse.model_validate(draft)


@router.post("/drafts/{draft_id}/cancel", response_model=OutreachDraftResponse, summary="Cancel a draft")
def cancel_draft(draft_id: int, session: Session = Depends(get_session),
                 role=Depends(_sales)) -> OutreachDraftResponse:
    draft = OutreachService(session).cancel(draft_id, actor="human")
    session.commit()
    return OutreachDraftResponse.model_validate(draft)


@router.post("/{draft_id}/send", response_model=OutreachDraftResponse,
             summary="Send an APPROVED draft (provider-confirmed; never auto/bulk)")
def send(draft_id: int, session: Session = Depends(get_session),
         role=Depends(_sales), _rl=Depends(_send_limit)) -> OutreachDraftResponse:
    draft = send_draft(session, draft_id, actor="human")
    session.commit()
    return OutreachDraftResponse.model_validate(draft)


@router.get("/providers/status", response_model=ProviderStatusResponse,
            summary="Truthful email/CRM provider status (no secrets)")
def providers_status(session: Session = Depends(get_session),
                     role=Depends(_viewer)) -> ProviderStatusResponse:
    settings = get_settings()
    email_status = email_provider_status(settings).value
    crm_status = crm_provider_status(settings).value
    note = {
        "NOT_CONFIGURED": "No email provider configured — outreach can be drafted and approved "
                          "but not sent until a provider is set.",
    }.get(email_status, "")
    return ProviderStatusResponse(
        email_provider=settings.email_provider, email_status=email_status, email_from=settings.email_from,
        crm_provider=settings.crm_provider, crm_status=crm_status,
        webhook_configured=bool(settings.webhook_secret), note=note,
    )
