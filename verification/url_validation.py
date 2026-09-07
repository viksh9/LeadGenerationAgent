"""Safe URL validation for evidence (reuses the existing collector safety layer).

Only validates that a URL is safe to (optionally) verify — never builds a crawler.
Live checks are opt-in; default verification makes no network calls.
"""

from __future__ import annotations

from typing import Optional

from collectors.company.safety import SafetyError, validate_public_url


def is_verifiable_url(url: Optional[str]) -> bool:
    """True if the URL is http/https and not an internal/private/localhost host."""
    if not url:
        return False
    try:
        validate_public_url(url, resolve=False)
        return True
    except SafetyError:
        return False


def safe_domain(url: Optional[str]) -> Optional[str]:
    if not url:
        return None
    try:
        return validate_public_url(url, resolve=False)
    except SafetyError:
        return None
