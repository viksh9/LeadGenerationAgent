"""ContactOut client exceptions.

Typed so callers (the POC discovery service, the test-connection endpoint) can map
upstream state to application behaviour WITHOUT ever fabricating data on failure.
No exception message ever contains the API token."""

from __future__ import annotations

from typing import Optional


class ContactOutError(RuntimeError):
    """Base for every ContactOut client error."""


class ContactOutNotConfigured(ContactOutError):
    """No CONTACTOUT_API_TOKEN configured — no request is ever attempted."""


class ContactOutAuthError(ContactOutError):
    """401/403 — token missing/invalid/forbidden. Never retried."""


class ContactOutRateLimitError(ContactOutError):
    """429 — rate limited (after client-side retries are exhausted)."""

    def __init__(self, message: str, *, retry_after: Optional[float] = None) -> None:
        super().__init__(message)
        self.retry_after = retry_after


class ContactOutUnavailableError(ContactOutError):
    """5xx / network error / timeout after retries."""


class ContactOutBadResponse(ContactOutError):
    """Malformed or unparseable response body."""
