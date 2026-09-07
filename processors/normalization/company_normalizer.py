"""Company + domain normalization (for matching, not display).

Preserves original_company_name; produces normalized_company_name (reusing the
shared normalizer), a normalized domain, and a company-identity confidence signal
for the FUTURE resolver. Does NOT merge companies. "ABC Technologies" is not
reduced to "ABC" — only legal suffixes are stripped.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional
from urllib.parse import urlsplit

from collectors.raw_record import normalize_company_name
from processors.normalization.text import clean_ws

_TRACKING_PREFIXES = ("utm_", "gclid", "fbclid", "mc_")


@dataclass
class NormalizedCompany:
    original_company_name: Optional[str]
    normalized_company_name: Optional[str]
    company_domain: Optional[str]
    company_identity_confidence: int
    warnings: list[str]


def normalize_domain(value: Optional[str]) -> Optional[str]:
    """Reduce a URL/host to a bare registrable-ish domain: no protocol, no www,
    no path/query. Does not guess a domain from a company name."""
    if not value or not value.strip():
        return None
    v = value.strip()
    if "//" not in v and " " not in v and "." in v and "/" not in v:
        host = v  # already a bare host
    else:
        if "//" not in v:
            v = "//" + v
        host = urlsplit(v).netloc or urlsplit(v).path.split("/")[0]
    host = host.lower().strip().rstrip(".")
    if host.startswith("www."):
        host = host[4:]
    host = host.split("/")[0].split(":")[0]
    return host or None


def _identity_confidence(name: Optional[str], domain: Optional[str], source_company_id: Optional[str]) -> int:
    conf = 0
    if name and len(name.strip()) >= 3:
        conf += 45
    if domain:
        conf += 40
    if source_company_id:
        conf += 15
    return min(100, conf)


def normalize_company(
    original_name: Optional[str],
    *,
    domain_or_url: Optional[str] = None,
    source_company_id: Optional[str] = None,
) -> NormalizedCompany:
    warnings: list[str] = []
    name = clean_ws(original_name)
    normalized = normalize_company_name(name) or None
    domain = normalize_domain(domain_or_url)
    if not name:
        warnings.append("company unclear")
    conf = _identity_confidence(name, domain, source_company_id)
    return NormalizedCompany(
        original_company_name=original_name,
        normalized_company_name=normalized,
        company_domain=domain,
        company_identity_confidence=conf,
        warnings=warnings,
    )
