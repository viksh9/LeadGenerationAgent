"""OpenCorporates client exceptions (Prompt 47).

Typed so the provider can map upstream state to a truthful status without ever
fabricating company data. No message ever contains the API token."""

from __future__ import annotations


class OpenCorporatesError(RuntimeError):
    """Base for every OpenCorporates client error."""


class OpenCorporatesNotConfigured(OpenCorporatesError):
    """No OPENCORPORATES_API_TOKEN configured — no request is attempted."""


class OpenCorporatesAuthError(OpenCorporatesError):
    """401/403 — token missing/invalid/forbidden. Never retried."""


class OpenCorporatesRateLimited(OpenCorporatesError):
    """429 — rate limited after client-side retries."""


class OpenCorporatesUnavailable(OpenCorporatesError):
    """5xx / network / timeout after retries."""


class OpenCorporatesBadResponse(OpenCorporatesError):
    """Malformed / unparseable response."""
