"""Public Contact Trust scoring + POC status (Prompt 45, §19/§22).

Contact Trust measures the RELIABILITY of a contact match and is kept strictly
separate from the business lead score (§31). Points are awarded only on real
evidence — never assigned without it, and never reaching 100 unless every criterion
is actually met.

Scoring (max 100):
    official company source          +35
    current company match            +25
    current title match              +20
    explicit public business email   +10
    explicit public business phone   +10
"""

from __future__ import annotations

from integrations.public_intelligence.models import (
    MATCH_LIKELY,
    MATCH_VERIFIED,
    STATUS_LIKELY,
    STATUS_UNVERIFIED,
    STATUS_VERIFIED,
)

OFFICIAL_SOURCE_POINTS = 35
CURRENT_COMPANY_POINTS = 25
CURRENT_TITLE_POINTS = 20
PUBLIC_EMAIL_POINTS = 10
PUBLIC_PHONE_POINTS = 10


def compute_contact_trust(*, official_source: bool, current_company_match: bool,
                          current_title_match: bool, public_business_email: bool,
                          public_business_phone: bool) -> int:
    score = 0
    if official_source:
        score += OFFICIAL_SOURCE_POINTS
    if current_company_match:
        score += CURRENT_COMPANY_POINTS
    if current_title_match:
        score += CURRENT_TITLE_POINTS
    if public_business_email:
        score += PUBLIC_EMAIL_POINTS
    if public_business_phone:
        score += PUBLIC_PHONE_POINTS
    return min(100, score)


def poc_status(*, company_match_status: str, current_title_match: bool) -> str:
    """Person-level POC status (§22). RECOMMENDED_ROLE_ONLY is handled separately
    (it applies when there is no person, only a recommended role)."""
    if company_match_status == MATCH_VERIFIED and current_title_match:
        return STATUS_VERIFIED
    if company_match_status in (MATCH_VERIFIED, MATCH_LIKELY):
        return STATUS_LIKELY
    return STATUS_UNVERIFIED
