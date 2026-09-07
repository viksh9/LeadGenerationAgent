"""Pydantic schema for AI reasoning output — every provider (LLM or deterministic)
must return this exact shape, and it is validated before persistence.

A claim is never a bare string: it carries a type (FACT/INFERENCE/UNKNOWN), a
support level, and the evidence_ids it is grounded in. This is what lets the UI
show facts and inferences distinctly and what the hallucination validator checks.
"""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, ConfigDict, Field

from database.models import ClaimSupportLevel, ClaimType


class AIClaim(BaseModel):
    model_config = ConfigDict(use_enum_values=True)

    claim_text: str
    claim_type: ClaimType = ClaimType.INFERENCE
    support_level: ClaimSupportLevel = ClaimSupportLevel.SUPPORTED_INFERENCE
    evidence_ids: list[int] = Field(default_factory=list)
    validation_status: Optional[str] = None    # set by the validator

    def as_dict(self) -> dict:
        return self.model_dump()


class AIIntelligenceOutput(BaseModel):
    """The validated AI reasoning payload (independent of persistence model)."""

    model_config = ConfigDict(use_enum_values=True)

    executive_summary: str = ""
    verified_facts: list[AIClaim] = Field(default_factory=list)
    inferred_insights: list[AIClaim] = Field(default_factory=list)
    unknowns: list[str] = Field(default_factory=list)
    opportunity_explanation: str = ""
    urgency_reason: str = ""
    business_problem_hypothesis: str = ""
    recommended_action: str = ""
    next_best_action: str = ""
    target_roles: list[str] = Field(default_factory=list)
    sales_angle: str = ""
    sales_pitch: str = ""
    risk_flags: list[str] = Field(default_factory=list)
    confidence: int = Field(default=0, ge=0, le=100)
