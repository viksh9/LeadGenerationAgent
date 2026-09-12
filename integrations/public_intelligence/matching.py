"""Deterministic company-match and role-relevance helpers (pure, no I/O).

Company match never succeeds on name similarity alone across different companies;
a domain match or a strong normalized-name overlap is required (§11/§21). Nothing
here fabricates data — it only classifies what a source actually returned.
"""

from __future__ import annotations

import re
from typing import Optional

from integrations.public_intelligence.models import (
    MATCH_LIKELY,
    MATCH_UNKNOWN,
    MATCH_VERIFIED,
    CompanyContext,
)

_SUFFIXES = {"inc", "inc.", "llc", "ltd", "ltd.", "limited", "pvt", "private", "gmbh",
             "corp", "corporation", "co", "company", "plc", "sa", "ag", "llp", "group",
             "technologies", "technology", "solutions", "services", "software", "systems",
             "global", "international", "india"}
_TECH_KEYWORDS = ("cto", "cio", "chief technology", "chief data", "chief information",
                  "vp engineering", "vice president of engineering", "head of engineering",
                  "engineering director", "director of engineering", "engineering manager",
                  "engineering lead", "staff engineer", "principal engineer", "platform lead",
                  "cloud engineer", "cloud architect", "infrastructure", "head of ai",
                  "head of data", "ml lead", "ai lead", "founder", "co-founder", "architect")


def normalize_company(text: Optional[str]) -> str:
    if not text:
        return ""
    text = re.sub(r"[^a-z0-9\s]", " ", text.lower())
    return " ".join(t for t in text.split() if t and t not in _SUFFIXES)


def domain_root(domain: Optional[str]) -> str:
    if not domain:
        return ""
    d = domain.lower().strip().replace("https://", "").replace("http://", "")
    return d.split("/")[0].removeprefix("www.")


def company_match(*, company_text: Optional[str], blog_or_domain: Optional[str],
                  ctx: CompanyContext) -> tuple[str, str]:
    """Classify a person's company association to the target. Returns (status, reason)."""
    tgt_domain = domain_root(ctx.domain) or domain_root(ctx.website)
    per_domain = domain_root(blog_or_domain)
    if tgt_domain and per_domain and (per_domain == tgt_domain or per_domain.endswith("." + tgt_domain)):
        return MATCH_VERIFIED, "Public profile links to the company domain."

    tgt = normalize_company(ctx.company_name)
    per = normalize_company(company_text)
    if tgt and per:
        if tgt == per:
            return MATCH_LIKELY, "Public profile lists the target company (self-reported)."
        tset, pset = set(tgt.split()), set(per.split())
        if tset and pset and (tset <= pset or pset <= tset):
            return MATCH_LIKELY, "Public profile company strongly overlaps the target."
    return MATCH_UNKNOWN, "Company association could not be confirmed from public data."


def is_technical(text: Optional[str]) -> bool:
    t = (text or "").lower()
    return any(k in t for k in _TECH_KEYWORDS)


def role_relevance(text: Optional[str], roles: list[str]) -> int:
    """0-100 relevance of a title/bio to the ordered recommended roles."""
    t = (text or "").lower()
    if not t:
        return 0
    best = 0
    for i, role in enumerate(roles):
        rtokens = [w for w in normalize_company(role).split()]
        if rtokens and all(w in t for w in rtokens):
            best = max(best, max(40, 100 - i * 10))
    if not best and is_technical(t):
        best = 50
    return best
