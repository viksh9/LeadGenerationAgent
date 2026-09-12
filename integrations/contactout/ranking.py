"""Deterministic POC ranking, company-match validation, and contact trust.

Pure functions — no I/O, no ContactOut calls. Ranking precedence (§9):
    current company match > current title relevance > seniority relevance
    > opportunity relevance > contact availability

Contact Trust (§17) is SEPARATE from the business lead score (§31): it answers
"how reliable is this contact match?", not "how valuable is this opportunity?".
Nothing here fabricates data — it only scores what ContactOut actually returned.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Optional

from integrations.contactout.models import ContactOutPerson

# Trust states (§17).
TRUST_VERIFIED = "VERIFIED"
TRUST_LIKELY = "LIKELY"
TRUST_UNVERIFIED = "UNVERIFIED"
TRUST_NO_CONTACT_DATA = "NO_CONTACT_DATA"

_SUFFIXES = {"inc", "inc.", "llc", "ltd", "ltd.", "limited", "pvt", "private", "gmbh",
             "corp", "corporation", "co", "company", "plc", "sa", "ag", "llp", "group",
             "technologies", "technology", "solutions", "services", "software", "systems",
             "global", "international", "india"}
_C_LEVEL = ("chief", "cto", "cio", "ceo", "cfo", "coo", "cdo", "cpo", "ciso")


def _norm(text: Optional[str]) -> str:
    if not text:
        return ""
    text = re.sub(r"[^a-z0-9\s]", " ", text.lower())
    tokens = [t for t in text.split() if t and t not in _SUFFIXES]
    return " ".join(tokens)


def _domain_root(domain: Optional[str]) -> str:
    if not domain:
        return ""
    d = domain.lower().strip().replace("https://", "").replace("http://", "")
    d = d.split("/")[0].removeprefix("www.")
    return d


@dataclass
class POCRanking:
    match_score: int = 0                 # 0-100 overall POC fit (ranking)
    company_matched: bool = False
    company_match_confidence: int = 0    # 0-100
    title_relevance: int = 0             # 0-100
    seniority_score: int = 0             # 0-100
    availability_score: int = 0          # 0-100
    trust_status: str = TRUST_UNVERIFIED
    trust_score: int = 0                 # 0-100 (contact reliability, NOT lead score)
    reasons: list[str] = field(default_factory=list)


def validate_company_match(
    person: ContactOutPerson, *, target_name: Optional[str], target_domain: Optional[str],
) -> tuple[bool, int, str]:
    """Confirm the person CURRENTLY works at the target company (§18). Name similarity
    alone never qualifies — a domain match or a strong normalized-name match plus
    current employment is required. Returns (matched, confidence 0-100, reason)."""
    # A person explicitly not in their current role is never a confident match.
    if person.is_current is False:
        return False, 0, "ContactOut marks this as a past role, not current employment."

    tgt_domain = _domain_root(target_domain)
    per_domain = _domain_root(person.company_domain)
    if tgt_domain and per_domain and tgt_domain == per_domain:
        return True, 100, "Company domain matches the target company."

    tgt_name = _norm(target_name)
    per_name = _norm(person.company_name)
    if tgt_name and per_name:
        if tgt_name == per_name:
            return True, 90, "Company name matches the target company."
        # One name fully contains the other's significant tokens (e.g. "Acme" vs "Acme Corp").
        tgt_tokens, per_tokens = set(tgt_name.split()), set(per_name.split())
        if tgt_tokens and per_tokens and (tgt_tokens <= per_tokens or per_tokens <= tgt_tokens):
            return True, 75, "Company name strongly overlaps the target company."
    return False, 0, "Could not confidently match the person's current company to the target."


def _title_relevance(job_title: Optional[str], recommended_roles: list[str]) -> tuple[int, bool]:
    """Relevance of the person's title to the ordered recommended roles.
    Returns (0-100 relevance, matched_any_recommended_role)."""
    title = _norm(job_title)
    if not title:
        return 0, False
    best = 0
    for i, role in enumerate(recommended_roles):
        role_tokens = set(_norm(role).split())
        if not role_tokens:
            continue
        overlap = role_tokens & set(title.split())
        if overlap:
            # Earlier recommended roles are worth more; require a meaningful overlap.
            coverage = len(overlap) / len(role_tokens)
            weight = max(40, 100 - i * 10)
            best = max(best, int(weight * coverage))
    return best, best > 0


def _seniority_score(person: ContactOutPerson) -> int:
    text = f"{person.seniority or ''} {person.job_title or ''}".lower()
    if any(k in text for k in _C_LEVEL):
        return 100
    if "vp" in text or "vice president" in text:
        return 90
    if "head" in text:
        return 85
    if "director" in text:
        return 80
    if "principal" in text or "lead" in text or "manager" in text:
        return 70
    return 50


def _availability_score(person: ContactOutPerson) -> int:
    score = 0
    if person.availability.work_email or person.work_email:
        score += 60
    if person.availability.phone or person.phone:
        score += 40
    return min(100, score)


def rank_person(
    person: ContactOutPerson, *, target_name: Optional[str], target_domain: Optional[str],
    recommended_roles: list[str],
) -> POCRanking:
    """Score a candidate POC. Precedence weights (sum to 1.0):
    company 0.40 > title 0.25 > seniority 0.15 > opportunity 0.10 > availability 0.10."""
    matched, company_conf, company_reason = validate_company_match(
        person, target_name=target_name, target_domain=target_domain)
    title_rel, opp_match = _title_relevance(person.job_title, recommended_roles)
    seniority = _seniority_score(person)
    availability = _availability_score(person)
    opportunity = 100 if opp_match else 0

    match_score = int(round(
        0.40 * company_conf + 0.25 * title_rel + 0.15 * seniority
        + 0.10 * opportunity + 0.10 * availability
    ))

    reasons = [company_reason]
    if title_rel:
        reasons.append("Title matches a recommended POC role for this opportunity.")
    if not availability:
        reasons.append("ContactOut returned no contact channel for this person.")

    trust_status, trust_score = _contact_trust(
        person, matched=matched, company_conf=company_conf, title_rel=title_rel)

    return POCRanking(
        match_score=match_score, company_matched=matched, company_match_confidence=company_conf,
        title_relevance=title_rel, seniority_score=seniority, availability_score=availability,
        trust_status=trust_status, trust_score=trust_score, reasons=reasons,
    )


def _contact_trust(person: ContactOutPerson, *, matched: bool, company_conf: int,
                   title_rel: int) -> tuple[str, int]:
    """Contact Trust status + score (§17). Never claims VERIFIED without the evidence."""
    has_contact = bool(person.work_email or person.phone or person.personal_email)
    if not has_contact:
        # No usable contact info — reliability is about the contact, and there is none.
        return TRUST_NO_CONTACT_DATA, min(40, company_conf // 2)

    score = 0
    if matched:
        score += 40
    if title_rel:
        score += 20
    if person.work_email:
        score += 15
        if person.work_email_verified:
            score += 15
    elif person.personal_email:
        score += 5   # personal email is a weaker business signal (§11)
    if person.phone:
        score += 10
    if person.linkedin_url:
        score += 10
    score = min(100, score)

    if matched and person.work_email_verified and title_rel and person.is_current is not False and score >= 80:
        return TRUST_VERIFIED, score
    if matched:
        return TRUST_LIKELY, score
    return TRUST_UNVERIFIED, score
