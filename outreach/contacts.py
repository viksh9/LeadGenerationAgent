"""Verified-contact helpers for outreach (§10).

A "verified business email" (safe to send to) requires ALL of:
* a populated ``business_email``,
* ``email_status == VERIFIED_SOURCE`` (published by a permitted source, never guessed),
* ``contact_type == BUSINESS_EMAIL`` (not a personal/profile contact),
* ``verification_status ∈ {VERIFIED, PARTIALLY_VERIFIED}``.

Emails are never generated from naming conventions and never SMTP-probed.
"""

from __future__ import annotations

import re

from sqlalchemy import select
from sqlalchemy.orm import Session

from database.models import (
    ContactType,
    DecisionMaker,
    EmailStatus,
    VerificationStatus,
)

_VERIFIED_STATUSES = {VerificationStatus.VERIFIED, VerificationStatus.PARTIALLY_VERIFIED}
_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def is_valid_email(value: str | None) -> bool:
    return bool(value and _EMAIL_RE.match(value.strip()))


def has_verified_business_email(contact: DecisionMaker) -> bool:
    if not is_valid_email(contact.business_email):
        return False
    if contact.email_status != EmailStatus.VERIFIED_SOURCE:
        return False
    if contact.contact_type != ContactType.BUSINESS_EMAIL:
        return False
    return contact.verification_status in _VERIFIED_STATUSES


def find_verified_contact_for_company(session: Session, company_id: int | None,
                                      normalized_company_name: str | None = None) -> DecisionMaker | None:
    """Return a decision-maker with a verified business email for the company, or
    None. Never fabricates a contact/email."""
    stmt = select(DecisionMaker).where(DecisionMaker.business_email.is_not(None))
    if company_id is not None:
        stmt = stmt.where(DecisionMaker.company_id == company_id)
    elif normalized_company_name:
        stmt = stmt.where(DecisionMaker.normalized_name.is_not(None),
                          DecisionMaker.company_name.is_not(None))
    candidates = session.execute(stmt.limit(100)).scalars().all()
    for c in candidates:
        if has_verified_business_email(c):
            return c
    return None
