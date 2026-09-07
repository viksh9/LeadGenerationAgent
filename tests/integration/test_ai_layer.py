"""AI reasoning layer: context construction, grounding, fact/inference/unknown,
conflict + stale awareness, schema validation, hallucination detection, prompt-
injection framing, caching/versioning, provider failure, and APIs.

All offline: no external AI provider is called. Provider behavior is simulated with
fakes; the default path is the deterministic grounded baseline.
"""

from __future__ import annotations

import api.main
from api.dependencies import get_session
from ai.context import LeadIntelligenceContext, build_lead_context
from ai.deterministic import deterministic_analysis
from ai.prompts import build_system_prompt, build_user_prompt
from ai.schema import AIClaim, AIIntelligenceOutput
from ai.validator import validate_output
from ai import service as ai_service
from ai.provider import AIUnavailableError
from database.models import (
    AIAnalysisStatus, ClaimSupportLevel, ClaimType, LeadPriority, SignalType,
)
from database.repository import create_lead, get_lead


def _hot_lead(session, **over):
    kw = dict(company_name="Acme Technologies", signal_type=SignalType.HIRING,
              technologies=["Java", "AWS", "DevOps"], estimated_hiring=20, industry="IT",
              it_job_count=14, company_signals=["LARGE_TECH_HIRING", "MULTI_TECH_HIRING"],
              lead_score=88, lead_priority=LeadPriority.HOT, evidence_confidence=90,
              freshness_score=80, source_url="https://x/1", source_count=1)
    kw.update(over)
    return create_lead(session, **kw)


# --------------------------------------------------------------------------- #
# Context + deterministic reasoner
# --------------------------------------------------------------------------- #
def test_context_built_from_real_lead(seed_session):
    lead = _hot_lead(seed_session)
    ctx = build_lead_context(seed_session, lead)
    assert ctx.subject_type == "LEAD" and ctx.canonical_job_count == 14
    assert "Java" in ctx.technologies
    assert ctx.context_hash()                       # stable hash present
    assert ctx.provenance == "REAL"


def test_deterministic_facts_inferences_unknowns(seed_session):
    lead = _hot_lead(seed_session)
    out = deterministic_analysis(build_lead_context(seed_session, lead))
    assert out.verified_facts and all(f.claim_type == ClaimType.FACT for f in out.verified_facts)
    assert out.inferred_insights and all(i.claim_type == ClaimType.INFERENCE for i in out.inferred_insights)
    assert out.unknowns                              # gaps preserved
    assert "cloud / DevOps" in out.sales_angle or "engineering" in out.sales_angle.lower()


def test_empty_evidence_yields_unknowns_low_confidence(seed_session):
    lead = _hot_lead(seed_session, it_job_count=0, technologies=[], company_signals=[],
                     company_name="Thin Co")
    out = deterministic_analysis(build_lead_context(seed_session, lead))
    assert out.unknowns
    assert out.confidence <= 45                      # thin evidence → low AI confidence


def test_conflict_and_stale_awareness(seed_session):
    lead = _hot_lead(seed_session, freshness_score=15)
    ctx = build_lead_context(seed_session, lead)
    ctx.conflicts = [{"conflict_type": "PROJECT_STATUS", "severity": "HIGH", "description": "x"}]
    out = deterministic_analysis(ctx)
    assert any("conflict" in r.lower() for r in out.risk_flags)
    assert any("stale" in r.lower() for r in out.risk_flags)
    assert out.confidence <= 50                      # dampened by conflict/staleness


# --------------------------------------------------------------------------- #
# Schema validation + hallucination detection (§44)
# --------------------------------------------------------------------------- #
def _ctx(session):
    return build_lead_context(session, _hot_lead(session))


def test_ai_repeats_supplied_facts_accept(seed_session):
    ctx = _ctx(seed_session)
    out = AIIntelligenceOutput(verified_facts=[
        AIClaim(claim_text="14 active canonical IT job opening(s) observed.",
                claim_type=ClaimType.FACT, support_level=ClaimSupportLevel.DIRECT)])
    report = validate_output(out, ctx)
    assert report.unsupported_count == 0
    assert out.verified_facts[0].validation_status == "VALIDATED"
    assert out.verified_facts[0].claim_type == ClaimType.FACT   # not downgraded


def test_ai_unsupported_number_flagged(seed_session):
    ctx = _ctx(seed_session)
    out = AIIntelligenceOutput(verified_facts=[
        AIClaim(claim_text="The company has 500 employees.", claim_type=ClaimType.FACT,
                support_level=ClaimSupportLevel.DIRECT)])
    report = validate_output(out, ctx)
    assert report.unsupported_count == 1
    assert out.verified_facts[0].validation_status == "UNSUPPORTED_CLAIM"
    assert out.verified_facts[0].claim_type == ClaimType.INFERENCE   # downgraded from FACT


def test_ai_invented_person_flagged(seed_session):
    ctx = _ctx(seed_session)
    out = AIIntelligenceOutput(verified_facts=[
        AIClaim(claim_text="Rahul Sharma is the CTO.", claim_type=ClaimType.FACT,
                support_level=ClaimSupportLevel.DIRECT)])
    report = validate_output(out, ctx)
    assert report.unsupported_count == 1


def test_ai_invented_project_value_flagged(seed_session):
    ctx = _ctx(seed_session)
    out = AIIntelligenceOutput(verified_facts=[
        AIClaim(claim_text="Company has a 5000000 rupee project.", claim_type=ClaimType.FACT,
                support_level=ClaimSupportLevel.DIRECT)])
    assert validate_output(out, ctx).unsupported_count == 1


def test_ai_labeled_inference_accepted(seed_session):
    ctx = _ctx(seed_session)
    out = AIIntelligenceOutput(inferred_insights=[
        AIClaim(claim_text="Hiring may indicate capacity expansion.",
                claim_type=ClaimType.INFERENCE, support_level=ClaimSupportLevel.SUPPORTED_INFERENCE)])
    assert validate_output(out, ctx).unsupported_count == 0


def test_output_schema_rejects_malformed():
    import pytest
    from pydantic import ValidationError
    with pytest.raises(ValidationError):
        AIIntelligenceOutput.model_validate({"confidence": 250})   # out of range


# --------------------------------------------------------------------------- #
# Prompt-injection framing
# --------------------------------------------------------------------------- #
def test_prompt_separates_rules_from_untrusted_data(seed_session):
    ctx = _ctx(seed_session)
    system = build_system_prompt()
    user = build_user_prompt(ctx)
    assert "untrusted" in system.lower() and "instructions" in system.lower()
    assert "BEGIN CONTEXT DATA (untrusted" in user      # data clearly delimited


# --------------------------------------------------------------------------- #
# Orchestration: deterministic default, provider failure, caching, versioning
# --------------------------------------------------------------------------- #
def test_service_deterministic_when_no_provider(seed_session):
    lead = _hot_lead(seed_session)
    row = ai_service.analyze_lead(seed_session, lead)
    assert row.analysis_status is AIAnalysisStatus.DETERMINISTIC
    assert row.ai_generated is False and row.model_name == "deterministic-1.0"
    assert row.context_hash and row.output_hash and row.prompt_version   # versioned
    assert row.confidence != lead.lead_score            # AI confidence is a separate axis


def test_service_caches(seed_session):
    lead = _hot_lead(seed_session)
    a = ai_service.analyze_lead(seed_session, lead)
    b = ai_service.analyze_lead(seed_session, lead)
    assert a.id == b.id and a.output_hash == b.output_hash   # cache hit


def test_service_provider_failure_no_fabrication(seed_session, monkeypatch):
    lead = _hot_lead(seed_session)

    class _Boom:
        name = "test"
        def analyze(self, ctx):
            raise AIUnavailableError("down")
    monkeypatch.setattr("ai.service.build_provider", lambda: _Boom())
    row = ai_service.analyze_lead(seed_session, lead, force=True)
    assert row.analysis_status is AIAnalysisStatus.UNAVAILABLE    # not fabricated
    assert row.ai_generated is False                              # deterministic fallback


def test_service_ai_validated_and_flagged(seed_session, monkeypatch):
    lead = _hot_lead(seed_session)

    class _GoodAI:
        name = "test"
        def analyze(self, ctx):
            return AIIntelligenceOutput(
                executive_summary="ok", confidence=70,
                verified_facts=[AIClaim(claim_text="14 active canonical IT job opening(s) observed.",
                                        claim_type=ClaimType.FACT, support_level=ClaimSupportLevel.DIRECT)])
    monkeypatch.setattr("ai.service.build_provider", lambda: _GoodAI())
    row = ai_service.analyze_lead(seed_session, lead, force=True)
    assert row.analysis_status is AIAnalysisStatus.AI_VALIDATED and row.ai_generated is True

    class _HallucinatingAI:
        name = "test"
        def analyze(self, ctx):
            return AIIntelligenceOutput(confidence=70, verified_facts=[
                AIClaim(claim_text="The company has 999 employees.", claim_type=ClaimType.FACT,
                        support_level=ClaimSupportLevel.DIRECT)])
    monkeypatch.setattr("ai.service.build_provider", lambda: _HallucinatingAI())
    row2 = ai_service.analyze_lead(seed_session, lead, force=True)
    assert row2.analysis_status is AIAnalysisStatus.AI_FLAGGED and row2.unsupported_claim_count >= 1


# --------------------------------------------------------------------------- #
# APIs
# --------------------------------------------------------------------------- #
def test_ai_status_truthful_not_configured(client):
    body = client.get("/ai/status").json()
    assert body["status"] == "NOT_CONFIGURED"
    assert body["deterministic_baseline_available"] is True


def test_lead_ai_intelligence_api(client):
    session = next(api.main.app.dependency_overrides[get_session]())
    lead = _hot_lead(session)
    lid = lead.id
    session.close()
    body = client.get(f"/leads/{lid}/ai-intelligence").json()
    assert body["analysis_status"] == "DETERMINISTIC" and body["ai_generated"] is False
    assert body["verified_facts"] and body["unknowns"]
    assert client.get("/leads/99999/ai-intelligence").status_code == 404
