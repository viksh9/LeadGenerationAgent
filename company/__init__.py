"""Company Intelligence & Entity Resolution.

Resolves the same real company across sources (domain-first, explainable, no
aggressive merging), preserves every source reference, supports corporate
relationships, and aggregates verified company-level intelligence. Reuses the
canonical-job, evidence-verification, and normalization foundations.
"""

from company.resolver import CompanyEntityResolver, CompanyResolutionResult  # noqa: F401
from company.service import CompanyIntelligenceService, CompanyResolutionService  # noqa: F401
