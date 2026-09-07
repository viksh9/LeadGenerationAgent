"""Safe text-normalization utilities.

Source content is treated as UNTRUSTED text — never executed or evaluated. These
helpers operate on COPIES and never mutate the caller's original value.
"""

from __future__ import annotations

import html
import re
import unicodedata
from typing import Optional

_WS_RE = re.compile(r"\s+")
_TAG_RE = re.compile(r"<[^>]+>")


def clean_ws(value: Optional[str]) -> Optional[str]:
    """Collapse whitespace and trim. Returns None for empty input."""
    if value is None:
        return None
    text = _WS_RE.sub(" ", value).strip()
    return text or None


def unaccent(value: str) -> str:
    """Strip diacritics (NFKD) for comparison only."""
    return "".join(c for c in unicodedata.normalize("NFKD", value) if not unicodedata.combining(c))


def normalize_for_compare(value: Optional[str]) -> str:
    """Lowercased, unaccented, whitespace-collapsed form for matching only."""
    if not value:
        return ""
    text = html.unescape(value)
    text = unaccent(text).lower()
    return _WS_RE.sub(" ", text).strip()


def strip_html(value: Optional[str]) -> Optional[str]:
    """Derive plain text from HTML: unescape entities and drop tags. Never
    executes anything — pure string operations. Original field is untouched."""
    if value is None:
        return None
    text = _TAG_RE.sub(" ", value)
    text = html.unescape(text)
    return clean_ws(text)


def title_case(value: str) -> str:
    """Title-case while keeping known acronyms upper and small words handled."""
    words = value.split()
    out = []
    for w in words:
        if w.upper() in _ACRONYMS:
            out.append(w.upper())
        elif w in _KEEP:
            out.append(_KEEP[w])
        else:
            out.append(w[:1].upper() + w[1:].lower() if w else w)
    return " ".join(out)


_ACRONYMS = {"AWS", "GCP", "SQL", "QA", "SDET", "SRE", "AI", "ML", "API", "UI", "UX", "IT", "HR"}
_KEEP = {".net": ".NET", "node.js": "Node.js", "c#": "C#", "react.js": "React.js"}
