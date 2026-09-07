"""IT-relevance classification for a single job: HIGH / MEDIUM / LOW / UNKNOWN.

Evidence-based and never title-only: combines role taxonomy, normalized
technologies, category/industry, and text. A single generic keyword does not make
a job HIGH; an obvious non-IT role with no tech is LOW.
"""

from __future__ import annotations

from enum import Enum
from typing import Optional

from collectors.it_taxonomy import NOT_RELEVANT, RELEVANT, classify_it_relevance
from processors.normalization.industry_normalizer import IndustryTaxonomy
from processors.normalization.role_normalizer import RoleTaxonomy

_ENGINEERING_ROLES = {r for r in RoleTaxonomy if r not in (RoleTaxonomy.OTHER, RoleTaxonomy.UNKNOWN)}
_IT_INDUSTRIES = {i for i in IndustryTaxonomy if i not in (IndustryTaxonomy.NON_IT, IndustryTaxonomy.UNKNOWN)}


class ITRelevance(str, Enum):
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"
    UNKNOWN = "UNKNOWN"


def is_it_relevant_job(
    *,
    title: Optional[str] = None,
    description: Optional[str] = None,
    technologies: Optional[list[str]] = None,
    role_taxonomy: RoleTaxonomy = RoleTaxonomy.UNKNOWN,
    industry: IndustryTaxonomy = IndustryTaxonomy.UNKNOWN,
) -> ITRelevance:
    techs = technologies or []
    base = classify_it_relevance(title, description)
    is_eng_role = role_taxonomy in _ENGINEERING_ROLES and role_taxonomy is not RoleTaxonomy.SOFTWARE_ENGINEERING
    it_industry = industry in _IT_INDUSTRIES

    # HIGH: clear engineering role with tech, or multiple techs, or role + IT industry.
    if (is_eng_role and techs) or len(techs) >= 2 or (is_eng_role and it_industry):
        return ITRelevance.HIGH
    # LOW: obvious non-IT with no tech signal.
    if base == NOT_RELEVANT and not techs and role_taxonomy in (RoleTaxonomy.OTHER, RoleTaxonomy.UNKNOWN):
        return ITRelevance.LOW
    # MEDIUM: some IT signal present.
    if techs or base == RELEVANT or role_taxonomy is not RoleTaxonomy.UNKNOWN or it_industry:
        return ITRelevance.MEDIUM
    return ITRelevance.UNKNOWN
