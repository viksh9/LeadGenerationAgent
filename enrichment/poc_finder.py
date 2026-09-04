"""Point-of-contact enrichment for LeadGenerationAgent.

Two APIs live here:

* ``POCEnricher`` (current) — a deterministic engine that recommends *who* to
  target (decision-maker personas) for an opportunity and ranks any known
  contacts supplied with the lead. No scraping, no external lookups, and no
  fabricated real people — only role/persona recommendations plus ranking of
  contacts the caller already has.
* ``find_points_of_contact`` / ``PointOfContact`` — the earlier helper, kept
  intact because other modules/tests import it.
"""

from collections.abc import Mapping
from dataclasses import dataclass
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field

from database.models import SignalType
from intelligence.opportunity_analyzer import OpportunityAssessment, OpportunityType
from intelligence.signal_detector import DetectedSignal, SignalDetectionResult

DECISION_TITLES = {
    "ceo": ("c-level", True, 0.95),
    "chief": ("c-level", True, 0.9),
    "founder": ("c-level", True, 0.92),
    "president": ("c-level", True, 0.88),
    "cto": ("c-level", True, 0.93),
    "cio": ("c-level", True, 0.93),
    "cfo": ("c-level", True, 0.85),
    "vp": ("vp", True, 0.82),
    "vice president": ("vp", True, 0.82),
    "head of": ("director", True, 0.78),
    "director": ("director", True, 0.7),
    "manager": ("manager", False, 0.45),
}

ROLE_HINTS = {
    "hiring": ("Head of Engineering", "director", True, 0.55),
    "project": ("VP of Operations", "vp", True, 0.6),
    "funding": ("Chief Executive Officer", "c-level", True, 0.58),
    "tech_stack": ("Chief Technology Officer", "c-level", True, 0.62),
    "expansion": ("VP of Growth", "vp", True, 0.5),
    "leadership": ("Chief of Staff", "director", False, 0.4),
}


@dataclass
class PointOfContact:
    full_name: str
    title: str | None
    email: str | None
    linkedin_url: str | None
    seniority: str
    is_decision_maker: bool
    confidence: float


def _classify_title(title: str | None) -> tuple[str, bool, float]:
    lowered = (title or "").lower()
    for needle, result in DECISION_TITLES.items():
        if needle in lowered:
            return result
    return ("unknown", False, 0.3)


def _synthetic_email(name: str, domain: str | None) -> str | None:
    if not domain:
        return None
    parts = [p for p in name.lower().replace(".", "").split() if p.isalpha() or p.replace("-", "").isalpha()]
    if len(parts) < 2:
        return None
    return f"{parts[0]}.{parts[-1]}@{domain}"


def find_points_of_contact(
    company_name: str,
    domain: str | None,
    signals: list[DetectedSignal],
    known_contacts: list[dict[str, Any]] | None = None,
) -> list[PointOfContact]:
    contacts: list[PointOfContact] = []
    for raw in known_contacts or []:
        name = (raw.get("full_name") or "").strip()
        if not name:
            continue
        seniority, is_dm, confidence = _classify_title(raw.get("title"))
        if raw.get("is_decision_maker") is True:
            is_dm = True
            confidence = max(confidence, 0.8)
        if raw.get("seniority"):
            seniority = raw["seniority"]
        contacts.append(
            PointOfContact(
                full_name=name,
                title=raw.get("title"),
                email=raw.get("email") or _synthetic_email(name, domain),
                linkedin_url=raw.get("linkedin_url"),
                seniority=seniority,
                is_decision_maker=is_dm,
                confidence=float(raw.get("confidence") or confidence),
            )
        )

    if not contacts:
        types = {s.signal_type for s in signals} or {"hiring"}
        primary_type = next((t for t in ("project", "funding", "tech_stack", "hiring") if t in types), "hiring")
        title, seniority, is_dm, confidence = ROLE_HINTS[primary_type]
        placeholder_name = f"{company_name} {title}"
        contacts.append(
            PointOfContact(
                full_name=placeholder_name,
                title=title,
                email=None,
                linkedin_url=None,
                seniority=seniority,
                is_decision_maker=is_dm,
                confidence=confidence,
            )
        )

    contacts.sort(key=lambda c: (c.is_decision_maker, c.confidence), reverse=True)
    return contacts


# ===========================================================================
# POC Enrichment Engine
# ===========================================================================
#
# Deterministic. Given the opportunity assessment + detected signals + whatever
# contact fields the lead already carries, it recommends which decision-maker
# personas to target and ranks any known contacts. It never invents real
# people: recommended contacts are role personas (no names), and only contacts
# explicitly supplied by the caller are ranked. No network / DB / LLM.


class Seniority(str, Enum):
    C_LEVEL = "C_LEVEL"
    VP = "VP"
    DIRECTOR = "DIRECTOR"
    HEAD = "HEAD"
    MANAGER = "MANAGER"
    LEAD = "LEAD"
    INDIVIDUAL = "INDIVIDUAL"
    UNKNOWN = "UNKNOWN"


class Department(str, Enum):
    EXECUTIVE = "EXECUTIVE"
    TECHNOLOGY = "TECHNOLOGY"
    ENGINEERING = "ENGINEERING"
    DELIVERY = "DELIVERY"
    PRODUCT = "PRODUCT"
    DIGITAL = "DIGITAL"
    PROCUREMENT = "PROCUREMENT"
    TALENT = "TALENT"
    OTHER = "OTHER"


class ContactPriority(str, Enum):
    PRIMARY = "PRIMARY"
    SECONDARY = "SECONDARY"


# -- Target persona rules (configurable): opportunity -> personas to pursue --
# Each persona is (title, department, seniority, is_decision_maker, priority).
_Persona = tuple[str, Department, Seniority, bool, ContactPriority]

TARGET_PERSONAS: dict[OpportunityType, tuple[_Persona, ...]] = {
    OpportunityType.LARGE_SCALE_RAMP_UP: (
        ("VP of Engineering", Department.ENGINEERING, Seniority.VP, True, ContactPriority.PRIMARY),
        ("Head of Delivery", Department.DELIVERY, Seniority.HEAD, True, ContactPriority.PRIMARY),
        ("Engineering Manager", Department.ENGINEERING, Seniority.MANAGER, False, ContactPriority.SECONDARY),
        ("Head of Talent Acquisition", Department.TALENT, Seniority.HEAD, False, ContactPriority.SECONDARY),
    ),
    OpportunityType.PROJECT_DRIVEN_HIRING: (
        ("Head of Delivery", Department.DELIVERY, Seniority.HEAD, True, ContactPriority.PRIMARY),
        ("Engineering Manager", Department.ENGINEERING, Seniority.MANAGER, True, ContactPriority.PRIMARY),
        ("Talent Acquisition Lead", Department.TALENT, Seniority.LEAD, False, ContactPriority.SECONDARY),
    ),
    OpportunityType.STAFF_AUGMENTATION: (
        ("Delivery Manager", Department.DELIVERY, Seniority.MANAGER, True, ContactPriority.PRIMARY),
        ("VP of Engineering", Department.ENGINEERING, Seniority.VP, True, ContactPriority.PRIMARY),
        ("Vendor Manager", Department.PROCUREMENT, Seniority.MANAGER, False, ContactPriority.SECONDARY),
    ),
    OpportunityType.VENDOR_OPPORTUNITY: (
        ("Head of Procurement / Vendor Management", Department.PROCUREMENT, Seniority.HEAD, True, ContactPriority.PRIMARY),
        ("Chief Technology Officer", Department.TECHNOLOGY, Seniority.C_LEVEL, True, ContactPriority.PRIMARY),
        ("IT Procurement Manager", Department.PROCUREMENT, Seniority.MANAGER, False, ContactPriority.SECONDARY),
    ),
    OpportunityType.TECHNOLOGY_IMPLEMENTATION: (
        ("Chief Technology Officer", Department.TECHNOLOGY, Seniority.C_LEVEL, True, ContactPriority.PRIMARY),
        ("Head of Engineering", Department.ENGINEERING, Seniority.HEAD, True, ContactPriority.PRIMARY),
        ("Delivery Manager", Department.DELIVERY, Seniority.MANAGER, False, ContactPriority.SECONDARY),
    ),
    OpportunityType.DIGITAL_TRANSFORMATION: (
        ("Chief Digital Officer", Department.DIGITAL, Seniority.C_LEVEL, True, ContactPriority.PRIMARY),
        ("Chief Technology Officer", Department.TECHNOLOGY, Seniority.C_LEVEL, True, ContactPriority.PRIMARY),
        ("Head of Digital Transformation", Department.DIGITAL, Seniority.HEAD, True, ContactPriority.SECONDARY),
    ),
    OpportunityType.NORMAL_HIRING: (
        ("Engineering Manager", Department.ENGINEERING, Seniority.MANAGER, False, ContactPriority.PRIMARY),
        ("Talent Acquisition Specialist", Department.TALENT, Seniority.INDIVIDUAL, False, ContactPriority.SECONDARY),
    ),
    OpportunityType.LOW_CONFIDENCE: (
        ("Talent Acquisition Contact", Department.TALENT, Seniority.UNKNOWN, False, ContactPriority.SECONDARY),
    ),
}

# -- Known-contact title classification (keyword -> seniority, dm, confidence)
# Order matters: the first matching keyword wins.
_TITLE_RULES: tuple[tuple[str, Seniority, bool, float], ...] = (
    ("ceo", Seniority.C_LEVEL, True, 0.95),
    ("founder", Seniority.C_LEVEL, True, 0.92),
    ("cto", Seniority.C_LEVEL, True, 0.93),
    ("cio", Seniority.C_LEVEL, True, 0.93),
    ("cdo", Seniority.C_LEVEL, True, 0.9),
    ("chief", Seniority.C_LEVEL, True, 0.9),
    ("president", Seniority.C_LEVEL, True, 0.88),
    ("vice president", Seniority.VP, True, 0.82),
    ("vp", Seniority.VP, True, 0.82),
    ("head of", Seniority.HEAD, True, 0.78),
    ("director", Seniority.DIRECTOR, True, 0.7),
    ("principal", Seniority.LEAD, False, 0.5),
    ("lead", Seniority.LEAD, False, 0.5),
    ("manager", Seniority.MANAGER, False, 0.45),
)

_RELEVANT_TITLE_HINTS = (
    "engineer", "engineering", "technology", "technical", "delivery",
    "procurement", "vendor", "digital", "developer", "platform", "it ",
)


class RecommendedContact(BaseModel):
    """A role persona to target (no real name — a recommendation, not a person)."""

    title: str
    department: Department
    seniority: Seniority
    is_decision_maker: bool
    priority: ContactPriority
    rationale: str


class ScoredContact(BaseModel):
    """A caller-supplied known contact, scored and ranked."""

    full_name: str
    title: Optional[str] = None
    email: Optional[str] = None
    linkedin_url: Optional[str] = None
    seniority: Seniority = Seniority.UNKNOWN
    is_decision_maker: bool = False
    confidence: float = 0.0
    suggested_email: Optional[str] = None


class POCEnrichmentResult(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    recommended_contacts: list[RecommendedContact] = Field(default_factory=list)
    primary_contact: Optional[RecommendedContact] = None
    ranked_known_contacts: list[ScoredContact] = Field(default_factory=list)
    best_known_contact: Optional[ScoredContact] = None
    target_departments: list[Department] = Field(default_factory=list)
    target_seniority: Seniority = Seniority.UNKNOWN
    outreach_focus: str = ""
    enrichment_confidence: int = 0
    enrichment_confidence_label: str = "LOW"


def _get(source: Any, key: str, default: Any = None) -> Any:
    if source is None:
        return default
    if isinstance(source, Mapping):
        return source.get(key, default)
    return getattr(source, key, default)


def _domain_from(website: Optional[str]) -> Optional[str]:
    if not website:
        return None
    text = str(website).strip().lower()
    for scheme in ("https://", "http://"):
        if text.startswith(scheme):
            text = text[len(scheme):]
    text = text.split("/")[0].strip()
    return text or None


def _suggest_email(full_name: str, domain: Optional[str]) -> Optional[str]:
    """Deterministic first.last@domain *pattern* suggestion (not a verified address)."""
    if not domain:
        return None
    parts = [p for p in full_name.strip().lower().split() if p.isalpha()]
    if len(parts) < 2:
        return None
    return f"{parts[0]}.{parts[-1]}@{domain}"


class POCEnricher:
    """Deterministic point-of-contact recommendation and ranking."""

    def enrich(
        self,
        lead_data: Any,
        signal_analysis: "SignalDetectionResult | dict | None" = None,
        opportunity: "OpportunityAssessment | dict | None" = None,
    ) -> POCEnrichmentResult:
        if isinstance(signal_analysis, dict):
            signal_analysis = SignalDetectionResult(**signal_analysis)
        if isinstance(opportunity, dict):
            opportunity = OpportunityAssessment(**opportunity)

        opp_type = (
            opportunity.opportunity_type if opportunity else OpportunityType.LOW_CONFIDENCE
        )
        opp_confidence = opportunity.opportunity_confidence if opportunity else 0

        recommended = self._recommended_personas(opp_type)
        primary = next((c for c in recommended if c.priority is ContactPriority.PRIMARY), None)
        primary = primary or (recommended[0] if recommended else None)

        ranked = self._rank_known_contacts(lead_data)
        best_known = ranked[0] if ranked else None

        primary_departments = [
            c.department for c in recommended if c.priority is ContactPriority.PRIMARY
        ] or [c.department for c in recommended]
        target_departments: list[Department] = []
        for dept in primary_departments:
            if dept not in target_departments:
                target_departments.append(dept)

        confidence, label = self._confidence(opp_type, opp_confidence, primary, ranked)

        return POCEnrichmentResult(
            recommended_contacts=recommended,
            primary_contact=primary,
            ranked_known_contacts=ranked,
            best_known_contact=best_known,
            target_departments=target_departments,
            target_seniority=primary.seniority if primary else Seniority.UNKNOWN,
            outreach_focus=self._outreach_focus(opp_type, primary),
            enrichment_confidence=confidence,
            enrichment_confidence_label=label,
        )

    # -- personas -----------------------------------------------------------

    @staticmethod
    def _recommended_personas(opp_type: OpportunityType) -> list[RecommendedContact]:
        personas = TARGET_PERSONAS.get(opp_type, TARGET_PERSONAS[OpportunityType.LOW_CONFIDENCE])
        result: list[RecommendedContact] = []
        for title, dept, seniority, is_dm, priority in personas:
            if is_dm and priority is ContactPriority.PRIMARY:
                rationale = "Likely decision-maker for this opportunity."
            elif is_dm:
                rationale = "Secondary decision-maker worth engaging."
            else:
                rationale = "Useful influencer or entry point for outreach."
            result.append(
                RecommendedContact(
                    title=title,
                    department=dept,
                    seniority=seniority,
                    is_decision_maker=is_dm,
                    priority=priority,
                    rationale=rationale,
                )
            )
        return result

    # -- known contacts -----------------------------------------------------

    def _rank_known_contacts(self, lead_data: Any) -> list[ScoredContact]:
        raw = self._collect_known_contacts(lead_data)
        domain = _domain_from(_get(lead_data, "company_website") or _get(lead_data, "domain"))
        scored: list[ScoredContact] = []
        for entry in raw:
            name = (entry.get("full_name") or "").strip()
            if not name:
                continue
            seniority, is_dm, confidence = self._classify_title(entry.get("title"))
            # Small boost when the title is clearly technology/delivery/procurement.
            if entry.get("title") and any(h in entry["title"].lower() for h in _RELEVANT_TITLE_HINTS):
                confidence = min(1.0, confidence + 0.05)
            if entry.get("is_decision_maker") is True:
                is_dm = True
                confidence = max(confidence, 0.8)
            email = entry.get("email")
            scored.append(
                ScoredContact(
                    full_name=name,
                    title=entry.get("title"),
                    email=email,
                    linkedin_url=entry.get("linkedin_url"),
                    seniority=seniority,
                    is_decision_maker=is_dm,
                    confidence=round(confidence, 2),
                    suggested_email=email or _suggest_email(name, domain),
                )
            )
        scored.sort(key=lambda c: (c.is_decision_maker, c.confidence), reverse=True)
        return scored

    @staticmethod
    def _collect_known_contacts(lead_data: Any) -> list[dict]:
        contacts: list[dict] = []
        listed = _get(lead_data, "contacts")
        if isinstance(listed, (list, tuple)):
            contacts.extend(dict(c) for c in listed if isinstance(c, Mapping))
        poc_name = _get(lead_data, "poc_name")
        if poc_name:
            contacts.append(
                {
                    "full_name": poc_name,
                    "title": _get(lead_data, "poc_title"),
                    "linkedin_url": _get(lead_data, "poc_linkedin_url"),
                    "email": _get(lead_data, "public_contact")
                    if "@" in str(_get(lead_data, "public_contact") or "")
                    else None,
                }
            )
        return contacts

    @staticmethod
    def _classify_title(title: Optional[str]) -> tuple[Seniority, bool, float]:
        lowered = (title or "").lower()
        for keyword, seniority, is_dm, confidence in _TITLE_RULES:
            if keyword in lowered:
                return seniority, is_dm, confidence
        return Seniority.UNKNOWN, False, 0.3

    # -- confidence + guidance ---------------------------------------------

    @staticmethod
    def _confidence(
        opp_type: OpportunityType,
        opp_confidence: int,
        primary: Optional[RecommendedContact],
        ranked: list[ScoredContact],
    ) -> tuple[int, str]:
        score = round(opp_confidence * 0.5)
        if primary and primary.is_decision_maker:
            score += 15
        if ranked:
            score += 20 if ranked[0].is_decision_maker else 10
        if opp_type is OpportunityType.LOW_CONFIDENCE:
            score = min(score, 40)
        value = max(0, min(100, int(score)))
        if value >= 80:
            label = "HIGH"
        elif value >= 50:
            label = "MEDIUM"
        else:
            label = "LOW"
        return value, label

    @staticmethod
    def _outreach_focus(opp_type: OpportunityType, primary: Optional[RecommendedContact]) -> str:
        if opp_type is OpportunityType.LOW_CONFIDENCE or primary is None:
            return "Insufficient signal to target a specific decision-maker; gather more information before outreach."
        department = primary.department.value.replace("_", " ").title()
        if primary.is_decision_maker:
            return f"Prioritize the {primary.title} in {department}; engage this decision-maker directly."
        return f"Prioritize the {primary.title} in {department}; use them to reach the decision-maker."


def run_poc_enrichment(
    lead_data: Any,
    signal_analysis: "SignalDetectionResult | dict | None" = None,
    opportunity: "OpportunityAssessment | dict | None" = None,
) -> POCEnrichmentResult:
    """Convenience wrapper using a default-configured enricher."""
    return POCEnricher().enrich(lead_data, signal_analysis, opportunity)


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
