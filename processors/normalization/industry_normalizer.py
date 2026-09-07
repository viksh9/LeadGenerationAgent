"""Industry label normalization -> configurable taxonomy. Original text kept by
the caller. Ambiguous/empty input -> UNKNOWN (never guessed).
"""

from __future__ import annotations

from enum import Enum
from typing import Optional

from processors.normalization.text import normalize_for_compare


class IndustryTaxonomy(str, Enum):
    IT_SERVICES = "IT_SERVICES"
    IT_CONSULTING = "IT_CONSULTING"
    SOFTWARE_PRODUCT = "SOFTWARE_PRODUCT"
    SAAS = "SAAS"
    CLOUD = "CLOUD"
    AI_ML = "AI_ML"
    CYBERSECURITY = "CYBERSECURITY"
    FINTECH_TECH = "FINTECH_TECH"
    HEALTHTECH = "HEALTHTECH"
    ECOMMERCE_TECH = "ECOMMERCE_TECH"
    ENTERPRISE_SOFTWARE = "ENTERPRISE_SOFTWARE"
    DIGITAL_TRANSFORMATION = "DIGITAL_TRANSFORMATION"
    OTHER_TECHNOLOGY = "OTHER_TECHNOLOGY"
    NON_IT = "NON_IT"
    UNKNOWN = "UNKNOWN"


# Ordered (specific first). Configurable.
_RULES: tuple[tuple[IndustryTaxonomy, tuple[str, ...]], ...] = (
    (IndustryTaxonomy.IT_CONSULTING, ("it consulting", "technology consulting", "it consultancy")),
    (IndustryTaxonomy.SAAS, ("saas", "software as a service")),
    (IndustryTaxonomy.CYBERSECURITY, ("cyber security", "cybersecurity", "information security", "infosec")),
    (IndustryTaxonomy.FINTECH_TECH, ("fintech", "financial technology")),
    (IndustryTaxonomy.HEALTHTECH, ("healthtech", "health tech", "healthcare technology")),
    (IndustryTaxonomy.ECOMMERCE_TECH, ("e-commerce", "ecommerce", "commerce technology")),
    (IndustryTaxonomy.AI_ML, ("artificial intelligence", "ai/ml", "machine learning", " ai ")),
    (IndustryTaxonomy.CLOUD, ("cloud services", "cloud technology", "cloud computing")),
    (IndustryTaxonomy.ENTERPRISE_SOFTWARE, ("enterprise software", "erp", "crm")),
    (IndustryTaxonomy.DIGITAL_TRANSFORMATION, ("digital transformation", "digital services")),
    (IndustryTaxonomy.IT_SERVICES, ("it services", "information technology & services", "technology services",
                                    "software services", "information technology and services")),
    (IndustryTaxonomy.SOFTWARE_PRODUCT, ("software product", "software development", "product engineering",
                                         "software", "information technology", " it ", "technology")),
)

_NON_IT = ("manufacturing", "logistics", "retail store", "hospitality", "construction",
           "agriculture", "textile", "warehouse", "facilities", "banking operations")


def normalize_industry(original: Optional[str]) -> IndustryTaxonomy:
    if not original or not original.strip():
        return IndustryTaxonomy.UNKNOWN
    text = f" {normalize_for_compare(original)} "
    for taxonomy, cues in _RULES:
        if any(c in text for c in cues):
            return taxonomy
    if any(c in text for c in _NON_IT):
        return IndustryTaxonomy.NON_IT
    return IndustryTaxonomy.UNKNOWN
