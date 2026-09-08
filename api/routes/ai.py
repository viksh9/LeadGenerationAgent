"""AI reasoning endpoints (grounded on real data; deterministic baseline always works).

GET returns cached/persisted intelligence (generating a deterministic baseline on
first request); POST forces a fresh analysis. When no AI provider is configured the
result is the deterministic grounded baseline — never a fabricated AI summary.
Provider status is truthful (CONNECTED only after a real model request).
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ai import service as ai_service
from ai.provider import config_status
from api.dependencies import get_session
from api.schemas import AIIntelligenceResponse, AIStatusResponse
from api.security import rate_limit
from company import repository as company_repo
from config.exceptions import NotFoundError
from config.settings import get_settings
from database.repository import get_lead

logger = logging.getLogger(__name__)
router = APIRouter(tags=["ai"])

# Rate limit forced AI analysis to protect the provider + control cost (§14, §46).
_ai_limit = rate_limit("ai_analyze", get_settings().ai_rate_per_minute)


@router.get("/ai/status", response_model=AIStatusResponse, summary="AI provider status (truthful)")
def ai_status() -> AIStatusResponse:
    settings = get_settings()
    status = config_status(settings).value
    note = {
        "NOT_CONFIGURED": "No AI provider configured — deterministic grounded reasoning is used.",
        "CONFIGURED": "AI provider configured; CONNECTED only after a verified model request.",
        "DISABLED": "AI provider explicitly disabled — deterministic reasoning is used.",
    }.get(status, "")
    return AIStatusResponse(
        provider=settings.ai_provider, model=settings.ai_model, status=status,
        deterministic_baseline_available=True, note=note,
    )


@router.get("/leads/{lead_id}/ai-intelligence", response_model=AIIntelligenceResponse,
            summary="AI reasoning for a lead (cached; generates baseline if missing)")
def lead_ai_intelligence(lead_id: int, session: Session = Depends(get_session)) -> AIIntelligenceResponse:
    lead = get_lead(session, lead_id)
    if lead is None:
        raise NotFoundError(f"Lead with id {lead_id} was not found.")
    result = ai_service.analyze_lead(session, lead)   # cached; deterministic if no provider
    return AIIntelligenceResponse.model_validate(result)


@router.post("/leads/{lead_id}/ai-analyze", response_model=AIIntelligenceResponse,
             summary="Force a fresh AI analysis for a lead", dependencies=[Depends(_ai_limit)])
def lead_ai_analyze(lead_id: int, session: Session = Depends(get_session)) -> AIIntelligenceResponse:
    lead = get_lead(session, lead_id)
    if lead is None:
        raise NotFoundError(f"Lead with id {lead_id} was not found.")
    result = ai_service.analyze_lead(session, lead, force=True)
    return AIIntelligenceResponse.model_validate(result)


@router.get("/companies/{company_id}/ai-intelligence", response_model=AIIntelligenceResponse,
            summary="AI reasoning for a company")
def company_ai_intelligence(company_id: int, session: Session = Depends(get_session)) -> AIIntelligenceResponse:
    company = company_repo.get_company(session, company_id)
    if company is None:
        raise NotFoundError(f"Company {company_id} not found.")
    result = ai_service.analyze_company(session, company)
    return AIIntelligenceResponse.model_validate(result)


@router.post("/companies/{company_id}/ai-analyze", response_model=AIIntelligenceResponse,
             summary="Force a fresh AI analysis for a company", dependencies=[Depends(_ai_limit)])
def company_ai_analyze(company_id: int, session: Session = Depends(get_session)) -> AIIntelligenceResponse:
    company = company_repo.get_company(session, company_id)
    if company is None:
        raise NotFoundError(f"Company {company_id} not found.")
    result = ai_service.analyze_company(session, company, force=True)
    return AIIntelligenceResponse.model_validate(result)
