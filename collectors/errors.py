"""Collector connection error taxonomy (shared across real-source clients).

Typed failures let the connectivity service classify a source's status truthfully
(AUTHENTICATION_FAILED vs RATE_LIMITED vs TEMPORARILY_UNAVAILABLE) instead of a
single opaque error. All are subclasses of ``CollectorError`` so existing
``except CollectorError`` handlers keep working.
"""

from __future__ import annotations


class CollectorError(RuntimeError):
    """Unrecoverable collector failure (config or non-retryable/exhausted HTTP)."""


class SourceAuthError(CollectorError):
    """Credentials are present but were rejected by the source (HTTP 401/403)."""


class SourceRateLimitError(CollectorError):
    """The source throttled the request (HTTP 429) and retries were exhausted."""


class SourceUnavailableError(CollectorError):
    """The source is temporarily unavailable (5xx / network / timeout)."""
