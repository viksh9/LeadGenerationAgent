"""AI analysis orchestration: context → (provider | deterministic) → validate → persist.

Design guarantees:
  * Deterministic authoritative: source data, scoring, verification are untouched;
    AI only adds narrative reasoning.
  * No fabrication on failure: if the provider is absent/unavailable, the
    deterministic grounded baseline is used (status UNAVAILABLE/DETERMINISTIC),
    never a fake AI summary.
  * Caching + versioning: cached by context_hash + prompt_version + model; re-run
    only on change or force.
  * Cost control: the LLM runs only for HOT/WARM leads (or force); others get the
    deterministic baseline.
  * Audited: every attempt writes an AIAnalysisAudit row (no sensitive data).
"""

from __future__ import annotations

import hashlib
import json
import logging
import time
from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from ai.context import LeadIntelligenceContext, build_company_context, build_lead_context
from ai.deterministic import deterministic_analysis
from ai.prompts import PROMPT_VERSION
from ai.provider import AIProviderError, build_provider
from ai.schema import AIIntelligenceOutput
from ai.validator import validate_output
from config.settings import get_settings
from database.models import (
    AIAnalysisAudit,
    AIAnalysisStatus,
    AIIntelligenceResult,
    DataProvenance,
    Lead,
    LeadPriority,
)

logger = logging.getLogger("ai")

_DETERMINISTIC_MODEL = "deterministic-1.0"
_AI_ELIGIBLE = {LeadPriority.HOT, LeadPriority.WARM}


def _output_hash(output: AIIntelligenceOutput) -> str:
    return hashlib.sha256(output.model_dump_json().encode()).hexdigest()


def _persist(session: Session, ctx: LeadIntelligenceContext, output: AIIntelligenceOutput, *,
             status: AIAnalysisStatus, ai_generated: bool, provider: Optional[str],
             model_name: Optional[str], unsupported: int) -> AIIntelligenceResult:
    from datetime import datetime, timezone
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    row = session.scalar(select(AIIntelligenceResult).where(
        AIIntelligenceResult.subject_type == ctx.subject_type,
        AIIntelligenceResult.subject_id == ctx.subject_id))
    if row is None:
        row = AIIntelligenceResult(subject_type=ctx.subject_type, subject_id=ctx.subject_id)
        session.add(row)
    row.company_id = ctx.company_id
    row.lead_id = ctx.lead_id
    row.executive_summary = output.executive_summary
    row.opportunity_explanation = output.opportunity_explanation
    row.urgency_reason = output.urgency_reason
    row.business_problem_hypothesis = output.business_problem_hypothesis
    row.recommended_action = output.recommended_action
    row.next_best_action = output.next_best_action
    row.sales_angle = output.sales_angle
    row.sales_pitch = output.sales_pitch
    row.verified_facts = [c.as_dict() for c in output.verified_facts]
    row.inferred_insights = [c.as_dict() for c in output.inferred_insights]
    row.unknowns = list(output.unknowns)
    row.risk_flags = list(output.risk_flags)
    row.target_roles = list(output.target_roles)
    row.evidence_ids = sorted({e for c in output.verified_facts for e in c.evidence_ids})
    row.source_ids = sorted({s for s in
                             [e.get("source") for e in ctx.evidence] if s})
    row.confidence = output.confidence
    row.analysis_status = status
    row.ai_generated = ai_generated
    row.unsupported_claim_count = unsupported
    row.provider = provider
    row.model_name = model_name
    row.prompt_version = PROMPT_VERSION
    row.context_hash = ctx.context_hash()
    row.output_hash = _output_hash(output)
    row.data_provenance = DataProvenance.REAL
    row.generated_at = now
    session.commit()
    return row


def _audit(session: Session, ctx: LeadIntelligenceContext, *, status: AIAnalysisStatus,
           provider: Optional[str], model_name: Optional[str], duration_ms: int,
           unsupported: int, error: Optional[str]) -> None:
    session.add(AIAnalysisAudit(
        subject_type=ctx.subject_type, subject_id=ctx.subject_id, provider=provider,
        model_name=model_name, prompt_version=PROMPT_VERSION, context_hash=ctx.context_hash(),
        status=status, duration_ms=duration_ms, unsupported_claim_count=unsupported,
        error=(error or None)))
    session.commit()


def get_ai_result(session: Session, subject_type: str, subject_id: int) -> Optional[AIIntelligenceResult]:
    return session.scalar(select(AIIntelligenceResult).where(
        AIIntelligenceResult.subject_type == subject_type,
        AIIntelligenceResult.subject_id == subject_id))


def analyze_lead(session: Session, lead: Lead, *, force: bool = False,
                 use_ai: bool = True) -> AIIntelligenceResult:
    """Analyze one lead. Uses a live LLM only when configured, connected, and the
    lead is HOT/WARM (or force); otherwise the deterministic grounded baseline."""
    ctx = build_lead_context(session, lead)
    return _analyze_context(session, ctx, force=force, use_ai=use_ai,
                            ai_eligible=force or (lead.lead_priority in _AI_ELIGIBLE))


def analyze_company(session: Session, company, *, force: bool = False,
                    use_ai: bool = True) -> AIIntelligenceResult:
    """Analyze one company from its aggregated real records (same guarantees)."""
    ctx = build_company_context(session, company)
    return _analyze_context(session, ctx, force=force, use_ai=use_ai, ai_eligible=force)


def _analyze_context(session: Session, ctx: LeadIntelligenceContext, *, force: bool,
                     use_ai: bool, ai_eligible: bool) -> AIIntelligenceResult:
    chash = ctx.context_hash()
    cached = get_ai_result(session, ctx.subject_type, ctx.subject_id)
    if (cached and not force and cached.context_hash == chash
            and cached.prompt_version == PROMPT_VERSION):
        return cached   # cache hit — do not call the provider on every request (§29)

    provider = build_provider() if (use_ai and ai_eligible) else None
    started = time.monotonic()
    error = None

    if provider is not None:
        try:
            output = provider.analyze(ctx)
            report = validate_output(output, ctx)
            status = AIAnalysisStatus.AI_FLAGGED if report.unsupported_count else AIAnalysisStatus.AI_VALIDATED
            row = _persist(session, ctx, output, status=status, ai_generated=True,
                           provider=provider.name, model_name=get_model_name(), unsupported=report.unsupported_count)
            _audit(session, ctx, status=status, provider=provider.name, model_name=get_model_name(),
                   duration_ms=int((time.monotonic() - started) * 1000),
                   unsupported=report.unsupported_count, error=None)
            return row
        except AIProviderError as exc:   # NO fabrication — fall back to deterministic
            error = str(exc)
            logger.warning("ai_provider_failed subject=%s id=%s error=%s",
                           ctx.subject_type, ctx.subject_id, exc)

    # Deterministic grounded baseline (also the honest path when AI unavailable).
    output = deterministic_analysis(ctx)
    status = AIAnalysisStatus.UNAVAILABLE if error else AIAnalysisStatus.DETERMINISTIC
    row = _persist(session, ctx, output, status=status, ai_generated=False,
                   provider=None, model_name=_DETERMINISTIC_MODEL, unsupported=0)
    _audit(session, ctx, status=status, provider=None, model_name=_DETERMINISTIC_MODEL,
           duration_ms=int((time.monotonic() - started) * 1000), unsupported=0, error=error)
    return row


def get_model_name() -> Optional[str]:
    return get_settings().ai_model
