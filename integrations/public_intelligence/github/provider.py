"""GitHub public-profile provider → normalized PublicPerson records.

Discovers technical POC candidates who publicly list the target company. A person is
included only when company association is at least LIKELY (§11) — name-alone never
qualifies. Email is taken ONLY when GitHub actually returns the public `email` field
(§10) — never derived. Executive status is never inferred from repo ownership (§12).
"""

from __future__ import annotations

from typing import Optional

import httpx

from integrations.public_intelligence.base import PublicIntelligenceProvider
from integrations.public_intelligence.github.client import GitHubClient
from integrations.public_intelligence.matching import company_match, is_technical, normalize_company
from integrations.public_intelligence.models import (
    MATCH_UNKNOWN,
    CompanyContext,
    PublicPerson,
)

# Keep GitHub calls bounded (anonymous rate limits are low): 1 search + a few fetches.
_MAX_CANDIDATES = 8


class GitHubProvider(PublicIntelligenceProvider):
    name = "github"
    source_label = "GitHub"
    source_type = "github_public_profile"

    def __init__(self, *, http: httpx.Client | None = None, sleep=None) -> None:
        self._client = GitHubClient(http=http, sleep=sleep)

    def health_check(self):
        from collectors.base import HealthStatus
        from integrations.public_intelligence.base import ProviderRateLimited, ProviderUnavailable
        try:
            self._client.get_org("github")   # public org — cheap, no enrichment
            return HealthStatus.HEALTHY, "GitHub public API reachable."
        except ProviderRateLimited:
            return HealthStatus.RATE_LIMITED, "GitHub rate limit reached."
        except ProviderUnavailable as exc:
            return HealthStatus.UNAVAILABLE, str(exc)

    def discover_people(self, ctx: CompanyContext, roles: list[str]) -> list[PublicPerson]:
        query = f'"{ctx.company_name}" in:company type:user'
        items = self._client.search_users(query, per_page=_MAX_CANDIDATES)
        people: list[PublicPerson] = []
        seen: set[str] = set()
        for item in items[:_MAX_CANDIDATES]:
            login = item.get("login")
            if not login or login in seen:
                continue
            seen.add(login)
            profile = self._client.get_user(login)
            if not isinstance(profile, dict):
                continue
            person = self._to_person(profile, ctx)
            if person and person.company_match_status != MATCH_UNKNOWN:
                people.append(person)
        return people

    def _to_person(self, p: dict, ctx: CompanyContext) -> Optional[PublicPerson]:
        name = p.get("name") or p.get("login")
        if not name:
            return None
        blog = p.get("blog") or None
        status, _reason = company_match(company_text=p.get("company"), blog_or_domain=blog, ctx=ctx)
        bio = p.get("bio")
        # Title is only inferred from an explicit technical bio phrase — never invented.
        job_title = bio if (bio and is_technical(bio)) else None
        return PublicPerson(
            full_name=name,
            job_title=job_title,
            company_name=p.get("company"),
            company_domain=None,
            linkedin_url=None,   # GitHub does not provide a LinkedIn URL; never guessed
            work_email=p.get("email") or None,   # ONLY if GitHub returned it publicly (§10)
            location=p.get("location"),
            bio=bio,
            is_current=None,     # GitHub does not assert current employment
            company_match_status=status,
            source=self.name, source_label=self.source_label, source_type=self.source_type,
            source_url=p.get("html_url"),
            source_record_id=str(p.get("id")) if p.get("id") is not None else p.get("login"),
        )
