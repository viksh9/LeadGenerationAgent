"""GitHub public REST API client (official api.github.com).

Anonymous public requests by default (§31); an optional GITHUB_API_TOKEN raises the
rate limit but is never required and never exposed. Only publicly returned fields
are used; no email is ever derived. GET-only via the shared PublicJsonClient.
"""

from __future__ import annotations

from typing import Any, Optional

import httpx

from config import get_settings
from integrations.public_intelligence.http import PublicJsonClient

_API = "https://api.github.com"


class GitHubClient:
    def __init__(self, *, http: httpx.Client | None = None, sleep=None) -> None:
        s = get_settings()
        headers = {"X-GitHub-Api-Version": "2022-11-28"}
        if s.github_api_token:
            headers["Authorization"] = f"Bearer {s.github_api_token}"
        kwargs: dict[str, Any] = dict(
            base_url=_API, user_agent=s.public_intelligence_user_agent,
            timeout_seconds=s.public_intelligence_timeout_seconds,
            requests_per_minute=s.github_rate_per_minute, headers=headers, http=http,
        )
        if sleep is not None:
            kwargs["sleep"] = sleep
        self._c = PublicJsonClient(**kwargs)

    def search_users(self, query: str, *, per_page: int = 10) -> list[dict]:
        data = self._c.get_json("/search/users", params={"q": query, "per_page": per_page},
                                provider="github")
        return (data or {}).get("items", []) if isinstance(data, dict) else []

    def get_user(self, login: str) -> Optional[dict]:
        return self._c.get_json(f"/users/{login}", provider="github")

    def get_org(self, login: str) -> Optional[dict]:
        return self._c.get_json(f"/orgs/{login}", provider="github")

    def get_org_public_members(self, login: str, *, per_page: int = 15) -> list[dict]:
        """PUBLIC members of an org (only those who chose to show membership). Members
        who keep membership private are never returned — no private data is inferred."""
        data = self._c.get_json(f"/orgs/{login}/public_members",
                                params={"per_page": per_page}, provider="github")
        return data if isinstance(data, list) else []
