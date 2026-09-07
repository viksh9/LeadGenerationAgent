"""Company → ATS/career-source discovery + verification (safe, deterministic).

Given a REAL company that already exists in our database (discovered from Adzuna /
Jooble / etc.), determine whether it publishes jobs via an official career page,
Greenhouse, or Lever — and VERIFY the company↔source relationship by only trusting
ATS identifiers found ON the company's own domain (its careers page links to, or
redirects to, a Greenhouse board / Lever site).

Safety (§34): all fetches go through the existing SafeHttpClient (HTTPS-upgrade,
SSRF guard, private-network block, validated redirects, response-size cap, polite
rate limit, transient-only retries, no credentials). We never blindly crawl — only
the company's own domain and its declared careers URL are probed. Board identifiers
are extracted from real evidence, never fabricated.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Optional

from collectors.company.config import load_career_config
from collectors.company.http_client import CareerCollectorError, SafeHttpClient
from collectors.company.safety import SafetyError, validate_public_url
from database.models import AtsProvider

logger = logging.getLogger("collectors.discovery")

# ATS identifier patterns (matched against the final URL + page HTML).
_GREENHOUSE_RES = (
    re.compile(r"(?:boards|job-boards)\.greenhouse\.io/(?:embed/job_board\?for=)?([a-z0-9][a-z0-9._-]{0,99})", re.I),
    re.compile(r"boards-api\.greenhouse\.io/v1/boards/([a-z0-9][a-z0-9._-]{0,99})", re.I),
    re.compile(r"greenhouse\.io/embed/job_board\?for=([a-z0-9][a-z0-9._-]{0,99})", re.I),
)
_LEVER_RES = (
    re.compile(r"jobs\.lever\.co/([a-z0-9][a-z0-9._-]{0,99})", re.I),
    re.compile(r"api\.lever\.co/v0/postings/([a-z0-9][a-z0-9._-]{0,99})", re.I),
)
# Identifiers that are never a real board (embed helpers / generic paths).
_STOPWORDS = {"embed", "job_board", "v1", "boards", "postings"}


@dataclass
class DiscoveryResult:
    company_id: Optional[int]
    company_name: Optional[str]
    provider: Optional[AtsProvider] = None
    board_identifier: Optional[str] = None
    careers_url: Optional[str] = None
    verified: bool = False
    discovery_method: Optional[str] = None
    detail: str = ""
    evidence_urls: list[str] = field(default_factory=list)


def _candidate_urls(domain: Optional[str], website: Optional[str], careers_url: Optional[str]) -> list[str]:
    """Deterministic, minimal set of URLs to probe — the company's own domain only."""
    urls: list[str] = []
    if careers_url:
        urls.append(careers_url)
    host = None
    if website:
        try:
            host = validate_public_url(website, resolve=False)
        except SafetyError:
            host = None
    host = host or (domain.strip().lower() if domain else None)
    if host:
        base = host if host.startswith("http") else f"https://{host}"
        urls.extend([f"{base}/careers", f"{base}/jobs", base])
    # De-dupe, preserve order.
    seen, out = set(), []
    for u in urls:
        if u and u not in seen:
            seen.add(u)
            out.append(u)
    return out


def _match(patterns, text: str) -> Optional[str]:
    for rx in patterns:
        for m in rx.finditer(text or ""):
            token = (m.group(1) or "").lower()
            if token and token not in _STOPWORDS:
                return token
    return None


def detect_ats(text: str, final_url: str) -> tuple[Optional[AtsProvider], Optional[str]]:
    """Return (provider, board_identifier) found in the page HTML / final URL."""
    haystack = f"{final_url}\n{text}"
    gh = _match(_GREENHOUSE_RES, haystack)
    if gh:
        return AtsProvider.GREENHOUSE, gh
    lv = _match(_LEVER_RES, haystack)
    if lv:
        return AtsProvider.LEVER, lv
    return None, None


def discover_career_source(
    *,
    company_id: Optional[int],
    company_name: Optional[str],
    domain: Optional[str] = None,
    website: Optional[str] = None,
    careers_url: Optional[str] = None,
    client: Optional[SafeHttpClient] = None,
) -> DiscoveryResult:
    """Probe the company's own domain to find + verify an ATS/career source.

    Makes real (safe) HTTP requests. Returns a DiscoveryResult; the caller persists
    it. Never fabricates a board id — returns verified=False when nothing is found.
    """
    result = DiscoveryResult(company_id=company_id, company_name=company_name)
    candidates = _candidate_urls(domain, website, careers_url)
    if not candidates:
        result.detail = "No company domain/website/careers URL to probe."
        return result

    client = client or SafeHttpClient(load_career_config())
    for url in candidates:
        try:
            page = client.fetch(url, enforce_content_type=False)
        except (SafetyError, CareerCollectorError) as exc:
            logger.info("discovery_fetch_failed url=%s error=%s", url, exc)
            continue
        provider, board = detect_ats(page.text, page.url)
        if provider and board:
            result.provider = provider
            result.board_identifier = board
            result.careers_url = url
            result.evidence_urls = [url, page.url] if page.url != url else [url]
            # Verified: the ATS identifier was found on the company's own careers
            # page (link) or via a redirect from it.
            result.verified = True
            result.discovery_method = (
                "careers_page_redirect" if page.url != url else "careers_page_link"
            )
            result.detail = (f"{provider.value} board '{board}' identified from the company's "
                             f"careers page ({url}).")
            return result

    result.detail = "No supported ATS (Greenhouse/Lever) found on the company's own domain."
    return result
