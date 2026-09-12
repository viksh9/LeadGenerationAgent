"""Multi-provider enrichment endpoints (Prompt 49): per-provider connectivity test,
admin status, and the lead contact-enrichment waterfall trigger.

Role-guarded (SALES) + rate-limited. Never exposes provider API keys. Live tests make
a real request only when a key is configured; NOT_CONFIGURED otherwise (never claims
LIVE_VERIFIED without an actual request).
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from api.dependencies import get_session
from api.schemas import (
    EnrichmentProviderStatus,
    EnrichmentStatusResponse,
    POCDiscoveryResponse,
    POCResponse,
    ProviderTestResponse,
)
from api.security import rate_limit, require_role
from collectors.base import HealthStatus
from config import get_settings
from config.exceptions import NotFoundError, ValidationError
from database.models import Lead, UserRole, utcnow
from enrichment.contact_enrichment import enrich_lead_contacts
from integrations.enrichment.registry import CAPABILITIES, build_provider

logger = logging.getLogger("integrations.enrichment")
router = APIRouter(tags=["enrichment"])

_role = require_role(UserRole.SALES)
_test_limit = rate_limit("enrichment_test", 20)
_enrich_limit = rate_limit("enrichment_run", 30)

_PROVIDERS = ("contactout", "apollo", "lusha", "prospeo", "hunter")
_HEALTH_TO_RESULT = {
    HealthStatus.HEALTHY: "LIVE_VERIFIED",
    HealthStatus.DEGRADED: "LIVE_VERIFIED",
    HealthStatus.AUTHENTICATION_FAILED: "AUTHENTICATION_FAILED",
    HealthStatus.RESTRICTED: "FORBIDDEN",
    HealthStatus.RATE_LIMITED: "RATE_LIMITED",
    HealthStatus.UNAVAILABLE: "SOURCE_UNAVAILABLE",
    HealthStatus.NOT_CONFIGURED: "NOT_CONFIGURED",
}


def _config_status(name: str) -> str:
    s = get_settings()
    if name == "contactout":
        return s.contactout_config_status
    return s.enrichment_provider_status(name)


@router.get("/integrations/enrichment/status", response_model=EnrichmentStatusResponse,
            summary="Enrichment provider config status + capabilities (no keys)")
def enrichment_status() -> EnrichmentStatusResponse:
    contactout_caps = {"decision_maker_search": True, "person_search": True, "person_enrichment": True}
    rows = []
    for name in _PROVIDERS:
        caps = (contactout_caps if name == "contactout"
                else {k: v for k, v in vars(CAPABILITIES[name]).items()} if name in CAPABILITIES else {})
        rows.append(EnrichmentProviderStatus(provider=name, status=_config_status(name), capabilities=caps))
    return EnrichmentStatusResponse(providers=rows)


@router.post("/integrations/{provider}/test", response_model=ProviderTestResponse,
             summary="Real per-provider connectivity test (no bulk enrichment)")
def provider_test(provider: str, role=Depends(_role), _rl=Depends(_test_limit)) -> ProviderTestResponse:
    provider = provider.lower()
    if provider not in _PROVIDERS:
        raise ValidationError(f"Unknown enrichment provider '{provider}'.")
    now = utcnow()
    if _config_status(provider) != "CONFIGURED":
        return ProviderTestResponse(provider=provider, result="NOT_CONFIGURED",
                                    message=f"{provider} is not configured.", performed_request=False,
                                    checked_at=now)
    if provider == "contactout":
        from integrations.contactout import ContactOutClient
        status, message = ContactOutClient().check_connection()
    else:
        inst = build_provider(provider)
        status, message = inst.health_check()
    return ProviderTestResponse(provider=provider, result=_HEALTH_TO_RESULT.get(status, "ERROR"),
                                message=message, performed_request=(status != HealthStatus.NOT_CONFIGURED),
                                checked_at=now)


@router.post("/leads/{lead_id}/contacts/enrich", response_model=POCDiscoveryResponse,
             summary="Run the multi-provider contact-enrichment waterfall for a lead")
def enrich_contacts(lead_id: int, force: bool = False, session: Session = Depends(get_session),
                    role=Depends(_role), _rl=Depends(_enrich_limit)) -> POCDiscoveryResponse:
    lead = session.get(Lead, lead_id)
    if lead is None:
        raise NotFoundError(f"Lead {lead_id} not found.")
    summ = enrich_lead_contacts(session, lead, force=force, actor=getattr(role, "value", str(role)))
    return POCDiscoveryResponse(
        lead_id=summ.lead_id, company_id=summ.company_id, company_name=summ.company_name,
        status=summ.status, candidates_found=len(summ.pocs), searches_used=summ.provider_calls,
        enrichments_used=summ.enrichments, persisted=summ.persisted, reason=summ.reason,
        pocs=[POCResponse.model_validate(p) for p in summ.pocs])
