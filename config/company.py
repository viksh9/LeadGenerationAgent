"""Configuration for company entity resolution (matching weights + thresholds).

Deterministic, explainable, accuracy over aggressive merging. All tuning here.
"""

from __future__ import annotations

from dataclasses import dataclass

COMPANY_RESOLUTION_VERSION = "1.0.0"


@dataclass(frozen=True)
class CompanyMatchConfig:
    # High-value factors.
    weight_domain_exact: int = 60
    weight_website_exact: int = 55
    weight_legal_name_exact: int = 40
    # Medium-value.
    weight_normalized_name_exact: int = 30
    weight_email_domain: int = 22
    weight_hq_city: int = 10
    # Low-value.
    weight_token_overlap: int = 18      # * token Jaccard
    weight_same_city: int = 6

    # Decision thresholds.
    exact_min: int = 60                 # a verified domain match alone -> EXACT
    high_min: int = 70
    possible_min: int = 40
    # A name that matches while the domain conflicts must never auto-merge.
    conflicting_domain_penalty: int = 40


DEFAULT_MATCH_CONFIG = CompanyMatchConfig()
