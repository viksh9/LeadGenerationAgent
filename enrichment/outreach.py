"""Deterministic outreach-readiness classification.

Outreach readiness is a SEPARATE axis from lead_score, evidence_confidence, and
person/contact confidence. It answers: given verified real intelligence, how ready
is this lead for outreach? A recommended role alone is never READY.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from database.models import OutreachReadiness


@dataclass
class OutreachInputs:
    opportunity_verified: bool = False       # verified/partially-verified opportunity
    company_resolved: bool = False           # canonical company identity established
    role_identified: bool = False            # at least one recommended stakeholder role
    has_verified_contact: bool = False       # a verified person or business contact
    evidence_stale: bool = False             # freshness failed / stale
    contradicted: bool = False               # unresolved critical contradiction


@dataclass
class OutreachResult:
    readiness: OutreachReadiness
    reasons: list[str] = field(default_factory=list)


def classify_outreach_readiness(inp: OutreachInputs) -> OutreachResult:
    reasons: list[str] = []
    if inp.contradicted or inp.evidence_stale:
        reasons.append("Evidence is stale or contradictory — hold.")
        return OutreachResult(OutreachReadiness.HOLD, reasons)
    if inp.opportunity_verified and inp.company_resolved and inp.role_identified and inp.has_verified_contact:
        reasons.append("Verified opportunity + company + target role + verified contact.")
        return OutreachResult(OutreachReadiness.READY, reasons)
    if inp.opportunity_verified and inp.role_identified and not inp.has_verified_contact:
        reasons.append("Opportunity + role identified, but no verified person/contact yet.")
        return OutreachResult(OutreachReadiness.ROLE_ONLY, reasons)
    reasons.append("Opportunity/contact evidence is insufficient — research required.")
    return OutreachResult(OutreachReadiness.RESEARCH_REQUIRED, reasons)
