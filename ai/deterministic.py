"""Deterministic, evidence-grounded reasoner — the always-available AI baseline.

Produces the SAME structured AIIntelligenceOutput as an LLM would, but with zero
hallucination risk: every fact is copied verbatim from the real context and carries
its evidence_ids; every interpretation is explicitly labelled INFERENCE with hedged
language ("may indicate", "evidence suggests"); gaps are listed as UNKNOWNs. It never
invents companies, people, numbers, dates, values, technologies, or intent.

This is what the platform shows when no LLM provider is connected (§11) — real
reasoning over real data, clearly not an LLM ("model_name=deterministic"). When an
LLM IS connected, its output is validated against this same grounded context.
"""

from __future__ import annotations

from ai.context import LeadIntelligenceContext
from ai.schema import AIClaim, AIIntelligenceOutput
from database.models import ClaimSupportLevel, ClaimType

# Technology → sales angle (deterministic, evidence-driven; recommendation only).
_ANGLES = [
    (("aws", "azure", "gcp", "cloud", "kubernetes", "devops"),
     "Offer cloud / DevOps engineering augmentation."),
    (("ai", "ml", "machine learning", "data engineering", "data science"),
     "Offer AI/ML & data engineering delivery support."),
    (("qa", "sdet", "automation testing", "test automation"),
     "Offer QA/SDET automation capacity."),
    (("cybersecurity", "security"), "Offer cybersecurity engineering support."),
    (("java", "python", "react", "angular", "node", "spring", ".net", "backend",
      "frontend", "full stack"), "Offer software engineering staff augmentation."),
]


def _evidence_ids(ctx: LeadIntelligenceContext) -> list[int]:
    return [e["evidence_id"] for e in ctx.evidence if e.get("evidence_id") is not None]


def _fact(text: str, evidence_ids: list[int]) -> AIClaim:
    return AIClaim(claim_text=text, claim_type=ClaimType.FACT,
                   support_level=ClaimSupportLevel.DIRECT, evidence_ids=evidence_ids)


def _inference(text: str, evidence_ids: list[int]) -> AIClaim:
    return AIClaim(claim_text=text, claim_type=ClaimType.INFERENCE,
                   support_level=ClaimSupportLevel.SUPPORTED_INFERENCE, evidence_ids=evidence_ids)


def _sales_angle(techs: list[str]) -> str:
    low = {t.lower() for t in techs}
    for needles, angle in _ANGLES:
        if any(needle in tech for tech in low for needle in needles):
            return angle
    return "Recommend discovery before proposing a specific engagement."


def deterministic_analysis(ctx: LeadIntelligenceContext) -> AIIntelligenceOutput:
    eids = _evidence_ids(ctx)
    facts: list[AIClaim] = []
    inferences: list[AIClaim] = []
    unknowns: list[str] = []
    risks: list[str] = []

    # ---- FACTS (verbatim from real data) ----
    if ctx.canonical_job_count:
        facts.append(_fact(
            f"{ctx.canonical_job_count} active canonical IT job opening(s) observed"
            + (f" ({ctx.recent_job_count} recent)." if ctx.recent_job_count else "."), eids))
    if ctx.technologies:
        top = ", ".join(ctx.technologies[:6])
        facts.append(_fact(f"Technologies observed across openings: {top}.", eids))
    if ctx.company_signals:
        facts.append(_fact("Company signals detected: " + ", ".join(ctx.company_signals[:6]) + ".", eids))
    for t in ctx.tenders[:3]:
        val = f" (value {t['estimated_value']} {t.get('currency') or ''})".rstrip() if t.get("estimated_value") else ""
        facts.append(_fact(f"Tender '{t.get('title')}' status {t.get('status')}{val}.",
                           [t["tender_id"]] if t.get("tender_id") else []))
    verified_people = [d for d in ctx.decision_makers if d.get("has_person")
                       and d.get("verification_status") in ("VERIFIED", "PARTIALLY_VERIFIED")]
    if verified_people:
        facts.append(_fact(f"{len(verified_people)} verified decision-maker record(s) on file.", eids))

    # ---- INFERENCES (labelled, hedged) ----
    if ctx.canonical_job_count >= 5 and ctx.technologies:
        inferences.append(_inference(
            "The concentration of current technology openings may indicate near-term "
            "engineering capacity requirements.", eids))
    if ctx.tenders and ctx.canonical_job_count:
        inferences.append(_inference(
            "Active procurement plus current hiring appears consistent with a potential "
            "delivery/vendor opportunity.", eids))
    if len(ctx.company_signals) >= 2:
        inferences.append(_inference(
            "Multiple corroborating signals suggest elevated technology delivery activity.", eids))

    # ---- UNKNOWNS (explicit gaps) ----
    if ctx.canonical_job_count and not ctx.tenders:
        unknowns.append("Actual hiring target / budget is not stated by any source.")
    if not verified_people:
        unknowns.append("No verified decision-maker identified yet.")
    if not ctx.tenders:
        unknowns.append("No procurement/vendor decision evidence available.")

    # ---- RISK FLAGS (conflict / staleness / resolution) ----
    if ctx.has_conflict:
        risks.append("Evidence is conflicting — verify before acting.")
    if ctx.is_stale:
        risks.append("Supporting evidence is stale; no recent corroboration found.")
    if ctx.company_id is None:
        risks.append("Company identity is not fully resolved.")

    # ---- Narrative (grounded) ----
    parts = []
    if ctx.canonical_job_count:
        parts.append(f"{ctx.company_name} has {ctx.canonical_job_count} active IT opening(s)")
        if ctx.technologies:
            parts.append("concentrated in " + ", ".join(ctx.technologies[:4]))
    opportunity_explanation = (
        (". ".join(p.capitalize() if i == 0 else p for i, p in enumerate(parts)) + ".")
        if parts else "Insufficient current evidence to explain a specific opportunity."
    )
    if inferences:
        opportunity_explanation += " " + inferences[0].claim_text

    urgency = ("Recent hiring/signal activity is fresh." if ctx.freshness_score >= 60
               else "No strong recency signal; treat urgency as low." if ctx.freshness_score
               else "Recency of the evidence is uncertain.")

    next_action = ("Verify current hiring activity on the official careers page and "
                   "identify the Head/VP of Engineering." if ctx.canonical_job_count
                   else "Collect more real signals before outreach.")
    if ctx.tenders:
        next_action = "Review the active tender's scope and closing date; validate the procurement contact."

    sales_angle = _sales_angle(ctx.technologies)
    problem = ("The evidence suggests a potential engineering-capacity gap; this is an "
               "inference, not a stated need.") if ctx.canonical_job_count else \
              "No business problem can be responsibly hypothesised from the current evidence."

    exec_summary = opportunity_explanation
    if unknowns:
        exec_summary += f" Key unknowns remain ({len(unknowns)})."

    # AI reasoning confidence — SEPARATE axis; scales with grounded evidence richness.
    confidence = min(90, 25 + 10 * len(facts) + 5 * len(inferences))
    if ctx.has_conflict:
        confidence = min(confidence, 45)
    if ctx.is_stale:
        confidence = min(confidence, 50)

    return AIIntelligenceOutput(
        executive_summary=exec_summary,
        verified_facts=facts, inferred_insights=inferences, unknowns=unknowns,
        opportunity_explanation=opportunity_explanation, urgency_reason=urgency,
        business_problem_hypothesis=problem,
        recommended_action=next_action, next_best_action=next_action,
        target_roles=[], sales_angle=sales_angle,
        sales_pitch=(ctx.opportunity_summary or ""),
        risk_flags=risks, confidence=confidence,
    )
