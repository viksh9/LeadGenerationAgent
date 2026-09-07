"""AI output grounding validator — detects hallucinated / unsupported claims.

Compares the entities in AI-generated FACT claims (numbers, technologies, named
people) against the real supplied context. Anything not traceable to the context is
marked UNSUPPORTED so the UI never presents it as a verified fact. This is the guard
that keeps an LLM from silently converting inference/unknown into fact (§26, §27).

Deterministic and conservative: when in doubt, downgrade rather than trust.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from ai.context import LeadIntelligenceContext
from ai.schema import AIClaim, AIIntelligenceOutput
from database.models import ClaimSupportLevel, ClaimType

_NUM_RE = re.compile(r"\b\d[\d,]*\b")
# A crude "Firstname Lastname" detector for flagging fabricated named people.
_PERSON_RE = re.compile(r"\b[A-Z][a-z]+\s+[A-Z][a-z]+\b")
_VALIDATED = "VALIDATED"
_UNSUPPORTED = "UNSUPPORTED_CLAIM"


@dataclass
class ValidationReport:
    unsupported_count: int
    flagged: list[str]


def _context_numbers(ctx: LeadIntelligenceContext) -> set[int]:
    nums: set[int] = {ctx.canonical_job_count, ctx.recent_job_count, ctx.source_count,
                      len(ctx.technologies), len(ctx.company_signals),
                      len([d for d in ctx.decision_makers if d.get("has_person")])}
    for t in ctx.tenders:
        if isinstance(t.get("estimated_value"), (int, float)):
            nums.add(int(t["estimated_value"]))
    return {n for n in nums if isinstance(n, int)}


def _context_people(ctx: LeadIntelligenceContext) -> set[str]:
    # The context intentionally carries no personal names (roles only), so ANY
    # "Firstname Lastname" in an AI fact is unsupported unless it is a company token.
    return set()


def _known_tokens(ctx: LeadIntelligenceContext) -> set[str]:
    toks: set[str] = set()
    for t in (ctx.technologies + ctx.company_signals):
        toks.update(re.findall(r"[a-z0-9]+", t.lower()))
    if ctx.company_name:
        toks.update(re.findall(r"[a-z0-9]+", ctx.company_name.lower()))
    return toks


def _claim_supported(claim: AIClaim, ctx: LeadIntelligenceContext,
                     numbers: set[int], people: set[str], tokens: set[str]) -> bool:
    text = claim.claim_text
    # Numbers in a FACT must exist in the context.
    for m in _NUM_RE.findall(text):
        try:
            val = int(m.replace(",", ""))
        except ValueError:
            continue
        if val > 1 and val not in numbers:
            return False
    # Named people in a FACT must be in the context (which carries none by design).
    for name in _PERSON_RE.findall(text):
        low = {w.lower() for w in name.split()}
        if not low.issubset(tokens) and name not in people:
            # Allow if it's actually a company/tech token pair; otherwise flag.
            return False
    return True


def validate_output(output: AIIntelligenceOutput, ctx: LeadIntelligenceContext) -> ValidationReport:
    """Mark each claim's validation_status; downgrade unsupported FACTs. Mutates output."""
    numbers = _context_numbers(ctx)
    people = _context_people(ctx)
    tokens = _known_tokens(ctx)
    flagged: list[str] = []

    def check(claims: list[AIClaim]) -> None:
        for claim in claims:
            supported = _claim_supported(claim, ctx, numbers, people, tokens)
            if supported:
                claim.validation_status = _VALIDATED
            else:
                claim.validation_status = _UNSUPPORTED
                # A FACT that isn't grounded is downgraded so the UI can't show it as fact.
                if claim.claim_type == ClaimType.FACT:
                    claim.claim_type = ClaimType.INFERENCE
                    claim.support_level = ClaimSupportLevel.UNSUPPORTED
                flagged.append(claim.claim_text)

    check(output.verified_facts)
    check(output.inferred_insights)
    return ValidationReport(unsupported_count=len(flagged), flagged=flagged)
