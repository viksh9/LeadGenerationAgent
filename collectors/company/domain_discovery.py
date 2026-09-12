"""CompanyDomainDiscoveryService (Prompt 48 §4).

Determines a company's OFFICIAL website domain from real signals already in the
system (company name, an existing domain, and a real source/job URL) — the input
to career-page discovery. It never guesses a domain from name similarity alone,
and it never treats an aggregator/ATS host (adzuna, jooble, greenhouse, linkedin…)
as the company's official domain. All URLs are SSRF-validated.

Statuses (§4): VERIFIED · POSSIBLE · REVIEW_REQUIRED · NOT_FOUND · CONFLICT.
The optional ``verify=True`` performs a real (safe) homepage fetch to confirm the
company name appears on the domain; the deterministic core needs no network.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from urllib.parse import urlparse

from collectors.company.safety import SafetyError, validate_public_url

logger = logging.getLogger(__name__)

# Hosts that are aggregators / ATS / social / job boards — NEVER a company's own
# official domain. A source URL on one of these does not establish the domain.
_NON_OFFICIAL_HOSTS = {
    "adzuna.com", "adzuna.in", "jooble.org", "indeed.com", "linkedin.com", "naukri.com",
    "monster.com", "glassdoor.com", "greenhouse.io", "boards.greenhouse.io", "lever.co",
    "jobs.lever.co", "workday.com", "myworkdayjobs.com", "smartrecruiters.com", "icims.com",
    "ashbyhq.com", "google.com", "bing.com", "facebook.com", "twitter.com", "x.com",
    "youtube.com", "instagram.com", "shine.com", "timesjobs.com", "foundit.in",
}

# Company-name suffixes/noise stripped before matching against a domain label.
_NAME_NOISE = re.compile(
    r"\b(private|pvt|limited|ltd|inc|incorporated|llc|llp|corp|corporation|company|co|"
    r"technologies|technology|tech|solutions|solution|systems|software|services|service|"
    r"consulting|consultancy|labs|global|international|india|group|holdings|digital)\b",
    re.IGNORECASE,
)
_ALNUM = re.compile(r"[^a-z0-9]+")


@dataclass
class DomainCandidate:
    domain: str
    source: str          # "existing_domain" | "source_url" | "website"
    name_match: str      # "strong" | "partial" | "none"


@dataclass
class DomainDiscoveryResult:
    company_name: str | None
    selected_domain: str | None = None
    status: str = "NOT_FOUND"     # VERIFIED | POSSIBLE | REVIEW_REQUIRED | NOT_FOUND | CONFLICT
    confidence: int = 0           # 0-100
    candidates: list[DomainCandidate] = field(default_factory=list)
    detail: str = ""
    evidence: list[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {
            "company_name": self.company_name, "selected_domain": self.selected_domain,
            "status": self.status, "confidence": self.confidence, "detail": self.detail,
            "candidates": [{"domain": c.domain, "source": c.source, "name_match": c.name_match}
                           for c in self.candidates],
            "evidence": self.evidence,
        }


def _norm_name_tokens(name: str | None) -> str:
    if not name:
        return ""
    stripped = _NAME_NOISE.sub(" ", name)
    return _ALNUM.sub("", stripped.lower())


def _host_of(url: str | None) -> str | None:
    if not url:
        return None
    raw = url.strip()
    if not raw:
        return None
    if "://" not in raw:
        raw = "https://" + raw
    try:
        host = validate_public_url(raw, resolve=False)   # SSRF-safe; returns host
    except SafetyError:
        return None
    host = (host or "").lower().lstrip("www.")
    return host or None


def _registrable(host: str) -> str:
    """Best-effort registrable domain (handles common in/co.in/com two-level TLDs)."""
    parts = host.split(".")
    if len(parts) <= 2:
        return host
    two_level = {"co.in", "com.au", "co.uk", "co.jp", "org.in", "net.in", "gov.in", "ac.in"}
    if ".".join(parts[-2:]) in two_level and len(parts) >= 3:
        return ".".join(parts[-3:])
    return ".".join(parts[-2:])


def _is_non_official(host: str) -> bool:
    reg = _registrable(host)
    return host in _NON_OFFICIAL_HOSTS or reg in _NON_OFFICIAL_HOSTS


def _name_match(name_tokens: str, domain: str) -> str:
    """Compare normalised company name against the domain's primary label."""
    if not name_tokens:
        return "none"
    label = _registrable(domain).split(".")[0]
    label = _ALNUM.sub("", label.lower())
    if not label:
        return "none"
    if label == name_tokens or name_tokens.startswith(label) or label.startswith(name_tokens):
        return "strong"
    if len(label) >= 4 and (label in name_tokens or name_tokens in label):
        return "partial"
    return "none"


class CompanyDomainDiscoveryService:
    def __init__(self, *, client=None):
        self._client = client   # optional SafeHttpClient for verify=True

    def discover(self, *, company_name: str | None, existing_domain: str | None = None,
                 source_url: str | None = None, website: str | None = None,
                 verify: bool = False) -> DomainDiscoveryResult:
        result = DomainDiscoveryResult(company_name=company_name)
        name_tokens = _norm_name_tokens(company_name)

        # Gather candidate registrable domains from real inputs (aggregators excluded).
        seen: dict[str, DomainCandidate] = {}
        for value, src in ((existing_domain, "existing_domain"), (website, "website"),
                           (source_url, "source_url")):
            host = _host_of(value)
            if not host or _is_non_official(host):
                continue
            reg = _registrable(host)
            if reg in seen:
                continue
            seen[reg] = DomainCandidate(reg, src, _name_match(name_tokens, reg))
        result.candidates = list(seen.values())

        if not result.candidates:
            result.detail = ("No official company domain could be derived from real signals "
                             "(source URL was an aggregator/ATS or missing).")
            return result

        strong = [c for c in result.candidates if c.name_match == "strong"]
        partial = [c for c in result.candidates if c.name_match == "partial"]

        # Conflict: two+ DISTINCT strong-match domains.
        distinct_strong = {c.domain for c in strong}
        if len(distinct_strong) > 1:
            result.status = "CONFLICT"
            result.detail = f"Multiple plausible official domains: {sorted(distinct_strong)}."
            return result

        if strong:
            chosen = strong[0]
            # VERIFIED when the strong match came from the company's OWN source URL
            # (the real posting linked to its own domain) or an existing verified domain.
            if chosen.source in ("source_url", "existing_domain"):
                result.status, result.confidence = "VERIFIED", 90
                result.detail = (f"Official domain '{chosen.domain}' confirmed — the real "
                                 f"{chosen.source.replace('_', ' ')} matches the company name.")
            else:
                result.status, result.confidence = "POSSIBLE", 70
                result.detail = f"Domain '{chosen.domain}' strongly matches the company name."
            result.selected_domain = chosen.domain
            result.evidence = [c.domain for c in result.candidates]
        elif partial:
            result.status, result.confidence = "REVIEW_REQUIRED", 45
            result.selected_domain = partial[0].domain
            result.detail = f"Domain '{partial[0].domain}' partially matches the company name; review."
        else:
            # Candidates exist but none matches the name — do not select on similarity alone.
            result.status, result.confidence = "REVIEW_REQUIRED", 30
            result.selected_domain = None
            result.detail = "Candidate domains found but none matches the company name; review required."

        if verify and result.selected_domain:
            self._verify_domain(result, name_tokens)
        return result

    def _verify_domain(self, result: DomainDiscoveryResult, name_tokens: str) -> None:
        """Optional real, SSRF-safe homepage check: confirm the company name appears."""
        try:
            from collectors.company.config import load_career_config
            from collectors.company.http_client import SafeHttpClient
            client = self._client or SafeHttpClient(load_career_config())
            page = client.try_fetch_text(f"https://{result.selected_domain}")
        except Exception:  # noqa: BLE001 — verification is best-effort, never fabricates
            page = None
        if not page:
            return
        page_tokens = _ALNUM.sub("", page.lower())
        if name_tokens and name_tokens in page_tokens and result.status == "POSSIBLE":
            result.status, result.confidence = "VERIFIED", 88
            result.detail += " Verified: company name present on the homepage."
