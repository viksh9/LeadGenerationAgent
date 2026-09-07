"""OPT-IN live AI test (real provider). SKIPPED by default.

Runs only when RUN_LIVE_AI_TESTS=true and AI provider credentials are present. It
validates ONLY schema + safety constraints (structured output, grounded/validated
claims) — never exact wording, and never persists into production intelligence here.
"""

from __future__ import annotations

import os

import pytest

_LIVE = os.environ.get("RUN_LIVE_AI_TESTS", "").lower() in {"1", "true", "yes"}

pytestmark = pytest.mark.skipif(
    not _LIVE, reason="live AI tests are opt-in (set RUN_LIVE_AI_TESTS=true + AI creds)"
)


def test_ai_provider_probe_and_schema(seed_session):
    from config.settings import Settings
    from ai.provider import OpenAICompatibleProvider, config_status
    from database.models import AIProviderStatus

    settings = Settings()
    if settings.ai_config_status != "CONFIGURED":
        pytest.skip("AI provider not configured (AI_API_KEY / AI_MODEL missing)")

    provider = OpenAICompatibleProvider(settings)
    status = provider.probe()                      # real model request
    assert isinstance(status, AIProviderStatus)
    assert status is AIProviderStatus.CONNECTED    # only if the request truly succeeded

    from database.repository import create_lead
    from database.models import SignalType, LeadPriority
    from ai.context import build_lead_context
    from ai.validator import validate_output

    lead = create_lead(seed_session, company_name="Acme Technologies", signal_type=SignalType.HIRING,
                       technologies=["Java", "AWS"], it_job_count=10, lead_priority=LeadPriority.HOT,
                       lead_score=80, evidence_confidence=85, source_url="https://x/1", source_count=1)
    ctx = build_lead_context(seed_session, lead)
    output = provider.analyze(ctx)                 # schema-validated by the provider
    # Safety: the grounding validator must run clean-ish; every fact carries evidence framing.
    validate_output(output, ctx)
    assert 0 <= output.confidence <= 100
