"""Deterministic company-type classification from verified evidence.

A company is NOT classified IT from a single software job — classification uses
industry text + technology mix + job categories, and returns a confidence.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from database.models import CompanyType

_CLOUD = {"AWS", "Azure", "GCP", "Kubernetes", "Docker", "DevOps", "Terraform"}
_AI = {"AI", "Machine Learning", "Generative AI", "Data Engineering"}
_SECURITY = {"Cybersecurity"}


@dataclass
class ClassificationResult:
    company_type: CompanyType
    company_types: list[str] = field(default_factory=list)
    confidence: int = 0
    evidence: list[str] = field(default_factory=list)


def classify_company(
    *,
    industry_text: Optional[str] = None,
    technologies: Optional[list[str]] = None,
    job_count: int = 0,
) -> ClassificationResult:
    text = (industry_text or "").lower()
    techs = set(technologies or [])
    types: list[CompanyType] = []
    evidence: list[str] = []

    def add(t: CompanyType, why: str):
        if t not in types:
            types.append(t)
            evidence.append(why)

    if any(k in text for k in ("fintech", "financial")):
        add(CompanyType.FINTECH_TECH, "industry mentions fintech")
    if "health" in text:
        add(CompanyType.HEALTHTECH, "industry mentions health")
    if any(k in text for k in ("security", "cyber")) or techs & _SECURITY:
        add(CompanyType.CYBERSECURITY, "security industry/tech")
    if any(k in text for k in ("e-commerce", "ecommerce", "commerce")):
        add(CompanyType.ECOMMERCE_TECH, "industry mentions e-commerce")
    if "saas" in text:
        add(CompanyType.SAAS, "industry mentions SaaS")
    if "consulting" in text:
        add(CompanyType.IT_CONSULTING if "it" in text or "tech" in text else CompanyType.CONSULTING, "consulting industry")
    if any(k in text for k in ("system integrator", "integration")):
        add(CompanyType.SYSTEM_INTEGRATOR, "system integration")
    if any(k in text for k in ("outsourcing", "managed services", "bpo")):
        add(CompanyType.OUTSOURCING, "outsourcing/managed services")
    if any(k in text for k in ("staffing", "recruitment", "talent")):
        add(CompanyType.STAFFING_TECH, "staffing/talent")
    if "cloud" in text or (techs & {"AWS", "Azure", "GCP"} and "Kubernetes" in techs):
        add(CompanyType.CLOUD, "cloud focus")
    if techs & _AI and len(techs & _AI) >= 2:
        add(CompanyType.AI_ML, "multiple AI/ML technologies")
    if any(k in text for k in ("it services", "technology services", "software services")):
        add(CompanyType.IT_SERVICES, "IT services industry")
    if any(k in text for k in ("software product", "product engineering")) or ("software" in text and "services" not in text):
        add(CompanyType.SOFTWARE_PRODUCT, "software product")
    if any(k in text for k in ("enterprise", "erp", "crm")):
        add(CompanyType.ENTERPRISE_SOFTWARE, "enterprise software")

    if not types:
        # Tech present but industry unclear -> OTHER_TECHNOLOGY; nothing -> UNKNOWN-ish.
        primary = CompanyType.OTHER_TECHNOLOGY if techs else CompanyType.OTHER_TECHNOLOGY
        conf = 30 if techs else 15
        return ClassificationResult(primary, [primary.value], conf, ["insufficient evidence" if not techs else "technologies present, industry unclear"])

    # Confidence: needs real evidence (industry text + enough jobs).
    conf = 50
    if industry_text:
        conf += 25
    if job_count >= 5:
        conf += 15
    if len(types) == 1:
        conf += 5
    return ClassificationResult(types[0], [t.value for t in types], min(100, conf), evidence)
