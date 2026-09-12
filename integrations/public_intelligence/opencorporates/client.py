"""OpenCorporates API client (Prompt 47).

Reuses the shared PublicJsonClient (retry/backoff/rate-limit/Retry-After). The API
token is passed as the documented `api_token` query parameter and is NEVER logged
(PublicJsonClient logs provider+attempt only, never the URL/params) and NEVER placed
in a user-facing URL. HTTPS only.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

import httpx


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)

from config import get_settings
from integrations.public_intelligence.base import (
    ProviderAuthError,
    ProviderRateLimited,
    ProviderUnavailable,
)
from integrations.public_intelligence.http import PublicJsonClient
from integrations.public_intelligence.opencorporates.exceptions import (
    OpenCorporatesAuthError,
    OpenCorporatesNotConfigured,
    OpenCorporatesRateLimited,
    OpenCorporatesUnavailable,
)


# In-memory diagnostics for the admin status endpoint (§40). Never holds secrets.
_DIAGNOSTICS: dict = {"last_success_at": None, "last_error": None}


def diagnostics() -> dict:
    return dict(_DIAGNOSTICS)


class OpenCorporatesClient:
    def __init__(self, *, http: httpx.Client | None = None, sleep=None) -> None:
        s = get_settings()
        self._token = s.opencorporates_api_token
        self._version = (s.opencorporates_api_version or "v0.4").strip("/")
        base = (s.opencorporates_base_url or "https://api.opencorporates.com").rstrip("/")
        kwargs = dict(base_url=f"{base}/{self._version}",
                      user_agent=s.public_intelligence_user_agent,
                      timeout_seconds=s.public_intelligence_timeout_seconds,
                      requests_per_minute=s.opencorporates_rate_per_minute, http=http)
        if sleep is not None:
            kwargs["sleep"] = sleep
        self._c = PublicJsonClient(**kwargs)

    @property
    def is_configured(self) -> bool:
        return bool(self._token)

    def _params(self, extra: dict) -> dict:
        params = {k: v for k, v in extra.items() if v is not None}
        params["api_token"] = self._token   # never logged / never surfaced to users
        return params

    def _get(self, path: str, params: dict):
        if not self._token:
            raise OpenCorporatesNotConfigured("OPENCORPORATES_API_TOKEN is not configured.")
        try:
            result = self._c.get_json(path, params=self._params(params), provider="opencorporates")
            _DIAGNOSTICS["last_success_at"] = _utcnow().isoformat()
            return result
        except ProviderAuthError as exc:
            _DIAGNOSTICS["last_error"] = "AUTHENTICATION_FAILED"
            raise OpenCorporatesAuthError(str(exc)) from exc
        except ProviderRateLimited as exc:
            _DIAGNOSTICS["last_error"] = "RATE_LIMITED"
            raise OpenCorporatesRateLimited(str(exc)) from exc
        except ProviderUnavailable as exc:
            _DIAGNOSTICS["last_error"] = "SOURCE_UNAVAILABLE"
            raise OpenCorporatesUnavailable(str(exc)) from exc

    def search_companies(self, name: str, *, jurisdiction_code: Optional[str] = None,
                         per_page: int = 10) -> Optional[dict]:
        """GET /companies/search?q=&jurisdiction_code=&per_page= (India-first when set)."""
        return self._get("/companies/search",
                         {"q": name, "jurisdiction_code": jurisdiction_code, "per_page": per_page})

    def get_company(self, jurisdiction_code: str, company_number: str) -> Optional[dict]:
        """GET /companies/{jurisdiction_code}/{company_number}."""
        return self._get(f"/companies/{jurisdiction_code}/{company_number}", {})
