"""Deterministic POC / decision-maker role recommendation.

``POCFinder`` recommends the decision-maker ROLE types most likely to own or
influence a technology/vendor/staffing decision. Phase 1 recommends roles only —
no real-person discovery, scraping, external APIs, or LLM.
"""

from collections.abc import Mapping
from dataclasses import dataclass
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field

from database.models import SignalType
from intelligence.opportunity_analyzer import OpportunityAssessment, OpportunityType
from intelligence.signal_detector import SignalDetectionResult


def _get(source, key, default=None):
    """Read a field from a dict or an object (duck-typed)."""
    if source is None:
        return default
    if isinstance(source, Mapping):
        return source.get(key, default)
    return getattr(source, key, default)


# ===========================================================================
# POC / Decision-Maker Intelligence
# ===========================================================================
#
# Deterministic role-recommendation engine. Given the detected signals, the
# opportunity analysis, and the lead's industry, it recommends the decision-maker
# ROLE TYPES most likely to own/influence the technology/vendor/staffing
# decision. Phase 1 recommends ROLES ONLY — no real-person discovery, no
# scraping, no external APIs, no LLM. All mappings live in configurable tables.


class RoleCategory(str, Enum):
    TECHNOLOGY_LEADERSHIP = "TECHNOLOGY_LEADERSHIP"
    ENGINEERING_LEADERSHIP = "ENGINEERING_LEADERSHIP"
    DELIVERY_LEADERSHIP = "DELIVERY_LEADERSHIP"
    PROGRAM_LEADERSHIP = "PROGRAM_LEADERSHIP"
    PROCUREMENT = "PROCUREMENT"
    VENDOR_MANAGEMENT = "VENDOR_MANAGEMENT"
    IT_SOURCING = "IT_SOURCING"
    BUSINESS_LEADERSHIP = "BUSINESS_LEADERSHIP"
    HR_TALENT = "HR_TALENT"


class DecisionMakerType(str, Enum):
    TECHNICAL = "TECHNICAL"
    BUSINESS = "BUSINESS"
    DELIVERY = "DELIVERY"
    PROCUREMENT = "PROCUREMENT"
    VENDOR = "VENDOR"
    HR = "HR"


# Role -> (category, decision-maker type, base authority 0-90). Central catalog.
ROLE_CATALOG: dict[str, tuple[RoleCategory, DecisionMakerType, int]] = {
    "CTO": (RoleCategory.TECHNOLOGY_LEADERSHIP, DecisionMakerType.TECHNICAL, 90),
    "CIO": (RoleCategory.TECHNOLOGY_LEADERSHIP, DecisionMakerType.TECHNICAL, 90),
    "Chief Digital Officer": (RoleCategory.TECHNOLOGY_LEADERSHIP, DecisionMakerType.TECHNICAL, 86),
    "Digital Transformation Head": (RoleCategory.TECHNOLOGY_LEADERSHIP, DecisionMakerType.TECHNICAL, 84),
    "Transformation Director": (RoleCategory.TECHNOLOGY_LEADERSHIP, DecisionMakerType.TECHNICAL, 82),
    "Director of Technology": (RoleCategory.TECHNOLOGY_LEADERSHIP, DecisionMakerType.TECHNICAL, 82),
    "Head of Technology": (RoleCategory.TECHNOLOGY_LEADERSHIP, DecisionMakerType.TECHNICAL, 82),
    "VP Engineering": (RoleCategory.ENGINEERING_LEADERSHIP, DecisionMakerType.TECHNICAL, 88),
    "Head of Engineering": (RoleCategory.ENGINEERING_LEADERSHIP, DecisionMakerType.TECHNICAL, 84),
    "Engineering Director": (RoleCategory.ENGINEERING_LEADERSHIP, DecisionMakerType.TECHNICAL, 80),
    "Engineering Manager": (RoleCategory.ENGINEERING_LEADERSHIP, DecisionMakerType.TECHNICAL, 72),
    "Technology Delivery Head": (RoleCategory.DELIVERY_LEADERSHIP, DecisionMakerType.DELIVERY, 80),
    "Delivery Head": (RoleCategory.DELIVERY_LEADERSHIP, DecisionMakerType.DELIVERY, 80),
    "Delivery Director": (RoleCategory.DELIVERY_LEADERSHIP, DecisionMakerType.DELIVERY, 80),
    "Program Director": (RoleCategory.PROGRAM_LEADERSHIP, DecisionMakerType.DELIVERY, 78),
    "Program Manager": (RoleCategory.PROGRAM_LEADERSHIP, DecisionMakerType.DELIVERY, 70),
    "Vendor Manager": (RoleCategory.VENDOR_MANAGEMENT, DecisionMakerType.VENDOR, 74),
    "IT Sourcing Manager": (RoleCategory.IT_SOURCING, DecisionMakerType.PROCUREMENT, 72),
    "Strategic Sourcing Manager": (RoleCategory.IT_SOURCING, DecisionMakerType.PROCUREMENT, 72),
    "Procurement Head": (RoleCategory.PROCUREMENT, DecisionMakerType.PROCUREMENT, 76),
    "IT Procurement Head": (RoleCategory.PROCUREMENT, DecisionMakerType.PROCUREMENT, 76),
    "Procurement Manager": (RoleCategory.PROCUREMENT, DecisionMakerType.PROCUREMENT, 68),
    "Business Unit Head": (RoleCategory.BUSINESS_LEADERSHIP, DecisionMakerType.BUSINESS, 78),
    "Talent Acquisition Head": (RoleCategory.HR_TALENT, DecisionMakerType.HR, 66),
    "HR Director": (RoleCategory.HR_TALENT, DecisionMakerType.HR, 64),
}

_DEFAULT_ROLE_META = (RoleCategory.BUSINESS_LEADERSHIP, DecisionMakerType.BUSINESS, 60)

# Signal -> (preferred roles, secondary roles). Ordered by relevance.
SIGNAL_ROLE_MAP: dict[SignalType, tuple[list[str], list[str]]] = {
    SignalType.HIRING: (
        ["VP Engineering", "Head of Engineering", "Engineering Director", "CTO", "Head of Technology"],
        ["Talent Acquisition Head", "HR Director"],
    ),
    SignalType.PROJECT_AWARD: (
        ["CTO", "CIO", "Program Director", "Delivery Head", "Business Unit Head"],
        ["Procurement Head", "Vendor Manager"],
    ),
    SignalType.PROJECT_EXECUTION: (
        ["Delivery Head", "Program Director", "Engineering Director", "Technology Delivery Head"],
        ["CTO", "Vendor Manager"],
    ),
    SignalType.DIGITAL_TRANSFORMATION: (
        ["CIO", "CTO", "Chief Digital Officer", "Head of Technology", "Transformation Director"],
        ["Program Director", "Delivery Head"],
    ),
    SignalType.TECHNOLOGY_INITIATIVE: (
        ["CTO", "CIO", "VP Engineering", "Head of Technology"],
        ["Engineering Director", "Program Director"],
    ),
    SignalType.VENDOR_REQUIREMENT: (
        ["Vendor Manager", "IT Sourcing Manager", "Procurement Head", "Strategic Sourcing Manager"],
        ["CTO", "CIO", "Delivery Head"],
    ),
    SignalType.CONTRACT: (
        ["Procurement Head", "Vendor Manager", "IT Sourcing Manager", "Business Unit Head"],
        ["CTO", "CIO", "Delivery Head"],
    ),
    SignalType.EXPANSION: (
        ["Business Unit Head", "VP Engineering", "Delivery Head"],
        ["Program Director"],
    ),
}

# Applied in addition to HIRING when the hiring volume is large.
LARGE_HIRING_ROLES: tuple[list[str], list[str]] = (
    ["VP Engineering", "CTO", "Head of Engineering", "Engineering Director"],
    ["Talent Acquisition Head", "Delivery Head"],
)

# Opportunity type value -> (primary roles, secondary roles).
OPPORTUNITY_ROLE_MAP: dict[str, tuple[list[str], list[str]]] = {
    "STAFF_AUGMENTATION": (
        ["VP Engineering", "Head of Engineering", "Engineering Director"],
        ["Delivery Head", "Vendor Manager"],
    ),
    "VENDOR_OPPORTUNITY": (
        ["Vendor Manager", "IT Sourcing Manager", "Procurement Head"],
        ["CTO", "CIO"],
    ),
    "LARGE_SCALE_RAMP_UP": (
        ["VP Engineering", "CTO", "Delivery Head"],
        ["Program Director", "Talent Acquisition Head"],
    ),
    "TECHNOLOGY_IMPLEMENTATION": (
        ["CTO", "CIO", "Program Director", "Delivery Head"],
        ["Engineering Director"],
    ),
    "DIGITAL_TRANSFORMATION": (
        ["CIO", "CTO", "Transformation Director"],
        ["Program Director", "Technology Delivery Head"],
    ),
    "PROJECT_DRIVEN_HIRING": (
        ["Delivery Head", "Engineering Director", "VP Engineering"],
        ["Program Director", "Talent Acquisition Head"],
    ),
    "NORMAL_HIRING": (
        ["Engineering Manager", "Engineering Director"],
        ["Talent Acquisition Head"],
    ),
}

# Normalized industry -> recommended roles (ordered).
INDUSTRY_ROLE_MAP: dict[str, list[str]] = {
    "IT": ["CTO", "VP Engineering", "Engineering Director", "Delivery Head", "Vendor Manager"],
    "BFSI": ["CIO", "CTO", "Technology Delivery Head", "IT Procurement Head", "Program Director"],
    "FMCG": ["CIO", "CTO", "Digital Transformation Head", "IT Procurement Head"],
    "HEALTHCARE": ["CIO", "CTO", "Digital Transformation Head", "Technology Delivery Head"],
}


@dataclass(frozen=True)
class POCFinderConfig:
    """Configurable role mappings and scoring weights."""

    role_catalog: Mapping[str, tuple] = None  # type: ignore[assignment]
    signal_roles: Mapping[SignalType, tuple] = None  # type: ignore[assignment]
    opportunity_roles: Mapping[str, tuple] = None  # type: ignore[assignment]
    industry_roles: Mapping[str, list] = None  # type: ignore[assignment]
    large_hiring_threshold: int = 10
    max_secondary_roles: int = 5

    def resolved(self) -> "POCFinderConfig":
        return POCFinderConfig(
            role_catalog=self.role_catalog or ROLE_CATALOG,
            signal_roles=self.signal_roles or SIGNAL_ROLE_MAP,
            opportunity_roles=self.opportunity_roles or OPPORTUNITY_ROLE_MAP,
            industry_roles=self.industry_roles or INDUSTRY_ROLE_MAP,
            large_hiring_threshold=self.large_hiring_threshold,
            max_secondary_roles=self.max_secondary_roles,
        )


def default_poc_config() -> POCFinderConfig:
    return POCFinderConfig().resolved()


class RoleRecommendation(BaseModel):
    role: str
    role_category: RoleCategory
    decision_maker_type: DecisionMakerType
    relevance_score: int
    reason: str


class POCRecommendationResult(BaseModel):
    """Structured POC recommendation, ready for the pipeline / frontend."""

    model_config = ConfigDict(from_attributes=True)

    primary_role: Optional[RoleRecommendation] = None
    secondary_roles: list[RoleRecommendation] = Field(default_factory=list)
    recommendation_confidence: int = 0
    recommendation_confidence_label: str = "LOW"
    reason: str = ""


def _normalize_industry(industry: Optional[str]) -> Optional[str]:
    if not industry:
        return None
    s = industry.lower()
    if any(k in s for k in ("bfsi", "bank", "financ", "insurance")):
        return "BFSI"
    if any(k in s for k in ("health", "pharma", "hospital", "clinic")):
        return "HEALTHCARE"
    if any(k in s for k in ("fmcg", "consumer goods", "cpg", "retail")):
        return "FMCG"
    if s == "it" or any(k in s for k in ("it services", "information technology", "software", "saas", "tech")):
        return "IT"
    return None


def _opp_type_value(opportunity: Any) -> Optional[str]:
    if opportunity is None:
        return None
    if isinstance(opportunity, dict):
        raw = opportunity.get("opportunity_type")
    else:
        raw = getattr(opportunity, "opportunity_type", None)
    return getattr(raw, "value", raw)


class POCFinder:
    """Deterministic decision-maker ROLE recommendation engine."""

    def __init__(self, config: Optional[POCFinderConfig] = None) -> None:
        self.config = (config or POCFinderConfig()).resolved()

    def recommend(
        self,
        lead_data: Any,
        signal_analysis: "SignalDetectionResult | dict",
        opportunity_analysis: Any = None,
    ) -> POCRecommendationResult:
        if isinstance(signal_analysis, dict):
            signal_analysis = SignalDetectionResult(**signal_analysis)
        cfg = self.config

        types = {t for t in signal_analysis.signal_types if t != SignalType.OTHER}
        hiring = signal_analysis.estimated_hiring
        if hiring is None:
            hiring = _get(lead_data, "estimated_hiring")
        hiring = hiring or 0
        industry = _normalize_industry(_get(lead_data, "industry"))
        opp_type = _opp_type_value(opportunity_analysis)

        # role -> accumulated evidence
        acc: dict[str, dict] = {}

        def add(roles, base, step, *, opp=False, signal=None, industry_hit=False, large=False):
            for idx, role in enumerate(roles):
                pts = max(0, base - idx * step)
                if pts <= 0:
                    continue
                rec = acc.setdefault(
                    role, {"pts": 0.0, "opp": False, "signals": set(), "industry": False, "large": False}
                )
                rec["pts"] += pts
                if opp:
                    rec["opp"] = True
                if signal is not None:
                    rec["signals"].add(signal)
                if industry_hit:
                    rec["industry"] = True
                if large:
                    rec["large"] = True

        # Opportunity mapping (strongest driver).
        if opp_type and opp_type in cfg.opportunity_roles:
            primary, secondary = cfg.opportunity_roles[opp_type]
            add(primary, 35, 4, opp=True)
            add(secondary, 18, 3, opp=True)

        # Signal mappings (summed across present signals).
        for stype in types:
            if stype in cfg.signal_roles:
                preferred, secondary = cfg.signal_roles[stype]
                add(preferred, 22, 3, signal=stype.value)
                add(secondary, 10, 2, signal=stype.value)

        # Large technology hiring as an additional driver.
        if SignalType.HIRING in types and hiring >= cfg.large_hiring_threshold:
            preferred, secondary = LARGE_HIRING_ROLES
            add(preferred, 22, 3, large=True)
            add(secondary, 10, 2, large=True)

        # Industry norms.
        if industry and industry in cfg.industry_roles:
            add(cfg.industry_roles[industry], 14, 2, industry_hit=True)

        recommendations = self._build_recommendations(acc, opp_type, industry)
        confidence, label = self._confidence(signal_analysis, types, hiring, industry, opp_type)

        if not recommendations:
            return POCRecommendationResult(
                primary_role=None,
                secondary_roles=[],
                recommendation_confidence=confidence,
                recommendation_confidence_label=label,
                reason="Insufficient signal or opportunity evidence to recommend a decision-maker role.",
            )

        primary = recommendations[0]
        secondary = recommendations[1 : 1 + cfg.max_secondary_roles]
        return POCRecommendationResult(
            primary_role=primary,
            secondary_roles=secondary,
            recommendation_confidence=confidence,
            recommendation_confidence_label=label,
            reason=self._overall_reason(primary, types, opp_type),
        )

    # -- helpers ------------------------------------------------------------

    def _build_recommendations(
        self, acc: dict[str, dict], opp_type: Optional[str], industry: Optional[str]
    ) -> list[RoleRecommendation]:
        recs: list[RoleRecommendation] = []
        for role, rec in acc.items():
            category, dm_type, base_weight = self.config.role_catalog.get(role, _DEFAULT_ROLE_META)
            authority = round(base_weight / 90 * 30)
            relevance = max(0, min(100, authority + int(min(rec["pts"], 70))))
            recs.append(
                RoleRecommendation(
                    role=role,
                    role_category=category,
                    decision_maker_type=dm_type,
                    relevance_score=relevance,
                    reason=self._role_reason(role, dm_type, rec, opp_type, industry),
                )
            )
        # Sort by relevance, then authority, then name — fully deterministic.
        recs.sort(
            key=lambda r: (
                -r.relevance_score,
                -self.config.role_catalog.get(r.role, _DEFAULT_ROLE_META)[2],
                r.role,
            )
        )
        return recs

    @staticmethod
    def _role_reason(
        role: str, dm_type: DecisionMakerType, rec: dict, opp_type: Optional[str], industry: Optional[str]
    ) -> str:
        parts: list[str] = []
        if rec["opp"] and opp_type:
            parts.append(f"the {opp_type.replace('_', ' ').lower()} opportunity")
        signals = sorted(rec["signals"])
        if rec["large"]:
            signals = ["large technology hiring"] + signals
        if signals:
            parts.append("signals (" + ", ".join(signals) + ")")
        if rec["industry"] and industry:
            parts.append(f"{industry} industry norms")
        basis = "; ".join(parts) if parts else "the available evidence"
        return f"{role} is a {dm_type.value.lower()} decision-maker recommended based on {basis}."

    @staticmethod
    def _overall_reason(primary: RoleRecommendation, types: set, opp_type: Optional[str]) -> str:
        signal_text = ", ".join(sorted(t.value for t in types)) or "the detected signals"
        opp_text = f" and a {opp_type.replace('_', ' ').lower()} opportunity" if opp_type else ""
        return (
            f"Based on {signal_text}{opp_text}, {primary.role} "
            f"({primary.decision_maker_type.value}) is the best-fit decision-maker."
        )

    @staticmethod
    def _confidence(
        signal: SignalDetectionResult,
        types: set,
        hiring: int,
        industry: Optional[str],
        opp_type: Optional[str],
    ) -> tuple[int, str]:
        conf = 0
        conf += 30 if signal.signal_strength >= 50 else (15 if signal.signal_strength > 0 else 0)
        if opp_type and opp_type != "LOW_CONFIDENCE":
            conf += 25
        if SignalType.VENDOR_REQUIREMENT in types or opp_type == "VENDOR_OPPORTUNITY":
            conf += 15
        if hiring > 0:
            conf += 15
        if types & {SignalType.PROJECT_AWARD, SignalType.PROJECT_EXECUTION, SignalType.CONTRACT}:
            conf += 15
        if industry is not None:
            conf += 10
        conf = max(0, min(100, conf))
        if conf >= 80:
            label = "HIGH"
        elif conf >= 50:
            label = "MEDIUM"
        else:
            label = "LOW"
        return conf, label


def run_poc_recommendation(
    lead_data: Any,
    signal_analysis: "SignalDetectionResult | dict",
    opportunity_analysis: Any = None,
) -> POCRecommendationResult:
    """Convenience wrapper using a default-configured POC finder."""
    return POCFinder().recommend(lead_data, signal_analysis, opportunity_analysis)
