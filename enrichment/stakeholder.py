"""Opportunity-specific stakeholder ROLE recommendations (reuses POCFinder).

Produces the recommended target roles for a real lead/opportunity — deterministic
and explainable — WITHOUT identifying any person. Role recommendation is not person
identification; a recommendation is never presented as a fact about a named
individual. Real people (when a permitted source verifies them) are handled
separately by the person enricher and stored as DecisionMaker rows.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

from database.models import RoleCategory as ModelRoleCategory
from enrichment.poc_finder import POCFinder, RoleCategory as PocRoleCategory
from intelligence.signal_detector import SignalDetectionResult

# Map the POC engine's role categories to the persisted RoleCategory taxonomy.
_CATEGORY_MAP = {
    PocRoleCategory.TECHNOLOGY_LEADERSHIP: ModelRoleCategory.TECHNICAL,
    PocRoleCategory.ENGINEERING_LEADERSHIP: ModelRoleCategory.ENGINEERING,
    PocRoleCategory.DELIVERY_LEADERSHIP: ModelRoleCategory.DELIVERY,
    PocRoleCategory.PROGRAM_LEADERSHIP: ModelRoleCategory.DELIVERY,
    PocRoleCategory.PROCUREMENT: ModelRoleCategory.PROCUREMENT,
    PocRoleCategory.VENDOR_MANAGEMENT: ModelRoleCategory.VENDOR_MANAGEMENT,
    PocRoleCategory.IT_SOURCING: ModelRoleCategory.PROCUREMENT,
    PocRoleCategory.BUSINESS_LEADERSHIP: ModelRoleCategory.BUSINESS,
    PocRoleCategory.HR_TALENT: ModelRoleCategory.TALENT_ACQUISITION,
}


@dataclass
class StakeholderRecommendation:
    role: str
    role_category: str
    decision_maker_type: str
    relevance_score: int
    reason: str
    is_primary: bool = False


@dataclass
class StakeholderResult:
    recommended_roles: list[StakeholderRecommendation] = field(default_factory=list)
    recommendation_confidence: int = 0
    recommendation_confidence_label: str = "LOW"
    reason: str = ""


def _to_recommendation(rec, *, primary: bool) -> StakeholderRecommendation:
    category = _CATEGORY_MAP.get(rec.role_category, ModelRoleCategory.OTHER)
    return StakeholderRecommendation(
        role=rec.role, role_category=category.value,
        decision_maker_type=rec.decision_maker_type.value,
        relevance_score=rec.relevance_score, reason=rec.reason, is_primary=primary,
    )


def recommend_stakeholders(
    lead_data: Any, signal_analysis: "SignalDetectionResult | dict",
    opportunity_analysis: Any = None, *, finder: Optional[POCFinder] = None,
) -> StakeholderResult:
    """Wrap POCFinder.recommend into a flat, opportunity-specific stakeholder list."""
    finder = finder or POCFinder()
    poc = finder.recommend(lead_data, signal_analysis, opportunity_analysis)
    roles: list[StakeholderRecommendation] = []
    if poc.primary_role:
        roles.append(_to_recommendation(poc.primary_role, primary=True))
    roles.extend(_to_recommendation(r, primary=False) for r in poc.secondary_roles)
    return StakeholderResult(
        recommended_roles=roles,
        recommendation_confidence=poc.recommendation_confidence,
        recommendation_confidence_label=poc.recommendation_confidence_label,
        reason=poc.reason,
    )


def recommend_for_lead(lead, *, finder: Optional[POCFinder] = None) -> StakeholderResult:
    """Recommend stakeholder roles from a stored Lead's real, persisted fields."""
    signal_types = [lead.signal_type] if getattr(lead, "signal_type", None) else []
    signal = SignalDetectionResult(
        signal_types=signal_types,
        detected_technologies=list(getattr(lead, "technologies", None) or []),
        estimated_hiring=getattr(lead, "estimated_hiring", None),
    )
    lead_data = {"industry": getattr(lead, "industry", None),
                 "estimated_hiring": getattr(lead, "estimated_hiring", None)}
    return recommend_stakeholders(lead_data, signal, None, finder=finder)
