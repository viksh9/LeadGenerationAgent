"""Career-page parsing strategies (structured data preferred; no JS execution).

Order of preference: JSON-LD schema.org JobPosting -> embedded application/json
-> minimal HTML anchors. Only structured data is parsed; page JavaScript is never
evaluated. Built on the stdlib html.parser (no third-party HTML dependency).
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from html.parser import HTMLParser
from typing import Any, Optional
from urllib.parse import urljoin

logger = logging.getLogger("collectors")

# A normalized job dict has these keys (any may be None/absent):
#   title, description, date_posted, valid_through, employment_type, company,
#   company_domain, location, city, state, country, remote, salary, url,
#   identifier, department


@dataclass
class ParseResult:
    jobs: list[dict] = field(default_factory=list)
    method: str = "none"
    next_url: Optional[str] = None


class _DomExtractor(HTMLParser):
    """Collects <script> blocks (by type), <a> links, and rel=next hints."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.scripts: list[tuple[str, str]] = []   # (type, content)
        self.anchors: list[tuple[str, str, str]] = []  # (href, rel, text)
        self.next_url: Optional[str] = None
        self._script_type: Optional[str] = None
        self._in_script = False
        self._a_href: Optional[str] = None
        self._a_rel: str = ""
        self._a_text: list[str] = []

    def handle_starttag(self, tag: str, attrs) -> None:
        d = {k.lower(): (v or "") for k, v in attrs}
        if tag == "script":
            self._in_script = True
            self._script_type = d.get("type", "").lower()
        elif tag == "a":
            self._a_href = d.get("href")
            self._a_rel = d.get("rel", "").lower()
            self._a_text = []
        elif tag == "link":
            if "next" in d.get("rel", "").lower() and d.get("href"):
                self.next_url = d["href"]

    def handle_data(self, data: str) -> None:
        if self._in_script and self._script_type is not None:
            self.scripts.append((self._script_type, data))
            self._script_type = None  # one data callback per CDATA script
        elif self._a_href is not None:
            self._a_text.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag == "script":
            self._in_script = False
            self._script_type = None
        elif tag == "a" and self._a_href is not None:
            text = " ".join(t.strip() for t in self._a_text if t.strip())
            self.anchors.append((self._a_href, self._a_rel, text))
            if "next" in self._a_rel and not self.next_url:
                self.next_url = self._a_href
            self._a_href = None


def _extract_dom(html: str) -> _DomExtractor:
    dom = _DomExtractor()
    try:
        dom.feed(html or "")
    except Exception as exc:  # noqa: BLE001 - malformed HTML must not crash collection
        logger.warning("html_parse_warning error=%s", exc)
    return dom


# --------------------------------------------------------------------------- #
# schema.org JobPosting normalization
# --------------------------------------------------------------------------- #
def _org(value: Any) -> tuple[Optional[str], Optional[str]]:
    """Return (name, domain) from a hiringOrganization value."""
    if isinstance(value, dict):
        name = value.get("name")
        domain = None
        url = value.get("url") or value.get("sameAs")
        if isinstance(url, str) and "//" in url:
            domain = url.split("//", 1)[1].split("/", 1)[0].lower() or None
        return (name, domain)
    if isinstance(value, str):
        return (value, None)
    return (None, None)


def _address(value: Any) -> dict:
    """Extract city/state/country + text from a jobLocation value."""
    locs = value if isinstance(value, list) else [value]
    for loc in locs:
        if not isinstance(loc, dict):
            continue
        addr = loc.get("address")
        if isinstance(addr, dict):
            city = addr.get("addressLocality")
            state = addr.get("addressRegion")
            country = addr.get("addressCountry")
            if isinstance(country, dict):
                country = country.get("name")
            text = ", ".join(str(x) for x in (city, state, country) if x)
            return {"city": city, "state": state, "country": country, "text": text or None}
        if isinstance(addr, str):
            return {"city": None, "state": None, "country": None, "text": addr}
    return {"city": None, "state": None, "country": None, "text": None}


def _salary(value: Any) -> Optional[str]:
    if not isinstance(value, dict):
        return None
    v = value.get("value")
    currency = value.get("currency") or ""
    if isinstance(v, dict):
        lo, hi, unit = v.get("minValue"), v.get("maxValue"), v.get("unitText")
        if lo is None and hi is None:
            lo = hi = v.get("value")
        if lo is None and hi is None:
            return None
        rng = f"{lo if lo is not None else '?'}-{hi if hi is not None else '?'}"
        return " ".join(p for p in (currency, rng, f"per {unit}".lower() if unit else "") if p).strip()
    if v is not None:
        return f"{currency} {v}".strip()
    return None


def _identifier(value: Any) -> Optional[str]:
    if isinstance(value, dict):
        v = value.get("value")
        return str(v) if v is not None else None
    if value is not None:
        return str(value)
    return None


def _is_remote(obj: dict, location: dict) -> Optional[bool]:
    if str(obj.get("jobLocationType", "")).upper() == "TELECOMMUTE":
        return True
    text = (location.get("text") or "").lower()
    if "remote" in text:
        return True
    return None


def normalize_jobposting(obj: dict, *, base_url: str = "") -> Optional[dict]:
    """Map a schema.org JobPosting object to the normalized job dict."""
    if not isinstance(obj, dict):
        return None
    if str(obj.get("@type", "")).lower() not in {"jobposting", ""} and "JobPosting" not in str(obj.get("@type", "")):
        return None
    name, domain = _org(obj.get("hiringOrganization"))
    location = _address(obj.get("jobLocation"))
    employment = obj.get("employmentType")
    if isinstance(employment, list):
        employment = ", ".join(str(e) for e in employment)
    url = obj.get("url")
    if url and base_url:
        url = urljoin(base_url, url)
    return {
        "title": obj.get("title"),
        "description": obj.get("description"),
        "date_posted": obj.get("datePosted"),
        "valid_through": obj.get("validThrough"),
        "employment_type": employment,
        "company": name,
        "company_domain": domain,
        "location": location["text"],
        "city": location["city"],
        "state": location["state"],
        "country": location["country"],
        "remote": _is_remote(obj, location),
        "salary": _salary(obj.get("baseSalary")),
        "url": url,
        "identifier": _identifier(obj.get("identifier")),
        "department": obj.get("occupationalCategory") or obj.get("industry"),
    }


def _walk_jsonld(node: Any):
    """Yield every dict in a JSON-LD tree (handles @graph and arrays)."""
    if isinstance(node, list):
        for item in node:
            yield from _walk_jsonld(item)
    elif isinstance(node, dict):
        yield node
        if "@graph" in node:
            yield from _walk_jsonld(node["@graph"])


# --------------------------------------------------------------------------- #
# Parsers
# --------------------------------------------------------------------------- #
class CareerPageParser:
    """Abstract parser strategy."""

    name = "abstract"

    def parse_jobs(self, html: str, *, base_url: str = "") -> list[dict]:  # pragma: no cover
        raise NotImplementedError

    def parse_job_detail(self, html: str, *, base_url: str = "") -> Optional[dict]:
        jobs = self.parse_jobs(html, base_url=base_url)
        return jobs[0] if jobs else None

    def detect_pagination(self, html: str, *, base_url: str = "") -> Optional[str]:
        nxt = _extract_dom(html).next_url
        return urljoin(base_url, nxt) if nxt and base_url else nxt


class JsonLdParser(CareerPageParser):
    name = "json-ld"

    def parse_jobs(self, html: str, *, base_url: str = "") -> list[dict]:
        jobs: list[dict] = []
        for stype, content in _extract_dom(html).scripts:
            if "ld+json" not in stype:
                continue
            try:
                data = json.loads(content.strip())
            except (json.JSONDecodeError, ValueError):
                continue
            for node in _walk_jsonld(data):
                if "JobPosting" in str(node.get("@type", "")):
                    job = normalize_jobposting(node, base_url=base_url)
                    if job:
                        jobs.append(job)
        return jobs


class EmbeddedJsonParser(CareerPageParser):
    """Parse job-like arrays out of <script type=application/json> blocks."""

    name = "embedded-json"
    _JOB_KEYS = ("title", "name", "jobTitle")
    _URL_KEYS = ("url", "absolute_url", "jobUrl", "hostedUrl", "applyUrl", "link")

    def parse_jobs(self, html: str, *, base_url: str = "") -> list[dict]:
        jobs: list[dict] = []
        for stype, content in _extract_dom(html).scripts:
            if stype != "application/json":
                continue
            try:
                data = json.loads(content.strip())
            except (json.JSONDecodeError, ValueError):
                continue
            for candidate in self._find_job_dicts(data):
                jobs.append(self._normalize(candidate, base_url))
        return jobs

    def _find_job_dicts(self, node: Any, depth: int = 0):
        if depth > 6:
            return
        if isinstance(node, dict):
            has_title = any(k in node for k in self._JOB_KEYS)
            has_url = any(k in node for k in self._URL_KEYS)
            if has_title and has_url:
                yield node
            for value in node.values():
                yield from self._find_job_dicts(value, depth + 1)
        elif isinstance(node, list):
            for item in node:
                yield from self._find_job_dicts(item, depth + 1)

    def _normalize(self, node: dict, base_url: str) -> dict:
        title = next((node[k] for k in self._JOB_KEYS if node.get(k)), None)
        url = next((node[k] for k in self._URL_KEYS if node.get(k)), None)
        if url and base_url:
            url = urljoin(base_url, str(url))
        loc = node.get("location")
        if isinstance(loc, dict):
            loc = loc.get("name") or loc.get("city")
        return {
            "title": title,
            "description": node.get("description") or node.get("content"),
            "date_posted": node.get("datePosted") or node.get("updated_at") or node.get("published_at"),
            "valid_through": node.get("validThrough"),
            "employment_type": node.get("employmentType") or node.get("type"),
            "company": (node.get("company") if isinstance(node.get("company"), str) else None),
            "company_domain": None,
            "location": loc if isinstance(loc, str) else None,
            "city": None, "state": None, "country": None, "remote": None,
            "salary": None,
            "url": url,
            "identifier": _identifier(node.get("id") or node.get("identifier")),
            "department": node.get("department") or node.get("team"),
        }


class HtmlJobParser(CareerPageParser):
    """Last-resort parser: job links from anchors (low fidelity)."""

    name = "html"
    _HINTS = ("job", "career", "position", "opening", "vacanc", "gh_jid", "lever.co")

    def parse_jobs(self, html: str, *, base_url: str = "") -> list[dict]:
        jobs: list[dict] = []
        seen: set[str] = set()
        for href, _rel, text in _extract_dom(html).anchors:
            if not href or not text:
                continue
            if not any(h in href.lower() for h in self._HINTS):
                continue
            url = urljoin(base_url, href) if base_url else href
            if url in seen:
                continue
            seen.add(url)
            jobs.append({
                "title": text, "description": None, "date_posted": None, "valid_through": None,
                "employment_type": None, "company": None, "company_domain": None,
                "location": None, "city": None, "state": None, "country": None, "remote": None,
                "salary": None, "url": url, "identifier": None, "department": None,
            })
        return jobs


# Strategy chain, highest fidelity first.
_STRATEGIES: tuple[CareerPageParser, ...] = (JsonLdParser(), EmbeddedJsonParser(), HtmlJobParser())


def parse_jobs(html: str, *, base_url: str = "") -> ParseResult:
    """Parse jobs from a listing page using the best available structured data."""
    for parser in _STRATEGIES:
        jobs = parser.parse_jobs(html, base_url=base_url)
        if jobs:
            next_url = parser.detect_pagination(html, base_url=base_url)
            return ParseResult(jobs=jobs, method=parser.name, next_url=next_url)
    return ParseResult(jobs=[], method="none", next_url=_STRATEGIES[0].detect_pagination(html, base_url=base_url))


def parse_job_detail(html: str, *, base_url: str = "") -> Optional[dict]:
    """Parse a single JobPosting from a detail page (JSON-LD preferred)."""
    return JsonLdParser().parse_job_detail(html, base_url=base_url)
