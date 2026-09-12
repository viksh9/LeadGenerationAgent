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
from integrations.public_intelligence.matching import (
    company_match,
    domain_root,
    is_technical,
    normalize_company,
)
from integrations.public_intelligence.models import (
    MATCH_UNKNOWN,
    MATCH_VERIFIED,
    CompanyContext,
    CompanyFieldEvidenceRecord,
    PublicCompanyFacts,
    PublicPerson,
)

# Keep GitHub calls bounded (anonymous rate limits are low): 1 search + a few fetches.
_MAX_CANDIDATES = 8
_MAX_MEMBERS = 10   # public org members fetched per company (bounded for rate limits)


class GitHubProvider(PublicIntelligenceProvider):
    name = "github"
    source_label = "GitHub"
    source_type = "github_public_profile"

    def __init__(self, *, http: httpx.Client | None = None, sleep=None) -> None:
        self._client = GitHubClient(http=http, sleep=sleep)
        self._org_cache: dict[str, Optional[dict]] = {}   # per-run org resolution cache

    def health_check(self):
        from collectors.base import HealthStatus
        from integrations.public_intelligence.base import ProviderAuthError, ProviderRateLimited, ProviderUnavailable
        try:
            self._client.get_org("github")   # public org — cheap, no enrichment
            return HealthStatus.HEALTHY, "GitHub public API reachable."
        except ProviderAuthError:
            return HealthStatus.AUTHENTICATION_FAILED, "Authentication failed."
        except ProviderRateLimited:
            return HealthStatus.RATE_LIMITED, "GitHub rate limit reached."
        except ProviderUnavailable as exc:
            return HealthStatus.UNAVAILABLE, str(exc)

    def _matched_org(self, ctx: CompanyContext) -> Optional[dict]:
        """Resolve the company's official GitHub ORGANIZATION — only on an exact
        normalized-name match AND (blog domain == company domain OR the company has no
        known domain). Never guessed (§4/§5). Cached per provider instance."""
        cache_key = normalize_company(ctx.company_name)
        if cache_key in self._org_cache:
            return self._org_cache[cache_key]
        result: Optional[dict] = None
        items = self._client.search_users(f'"{ctx.company_name}" type:org', per_page=5)
        tgt_name = normalize_company(ctx.company_name)
        tgt_domain = domain_root(ctx.domain) or domain_root(ctx.website)
        for item in items[:5]:
            login = item.get("login")
            if not login:
                continue
            org = self._client.get_org(login)
            if not isinstance(org, dict):
                continue
            org_name = normalize_company(org.get("name") or org.get("login"))
            blog_domain = domain_root(org.get("blog"))
            name_ok = bool(org_name) and org_name == tgt_name
            domain_ok = bool(tgt_domain) and blog_domain == tgt_domain
            if name_ok and (domain_ok or bool(tgt_domain) is False) and org.get("html_url"):
                result = org
                break
        self._org_cache[cache_key] = result
        return result

    def discover_company(self, ctx: CompanyContext) -> Optional[PublicCompanyFacts]:
        """Find the company's official GitHub ORGANIZATION (evidence-matched; supporting
        source only, §4/§5)."""
        org = self._matched_org(ctx)
        if org is None:
            return None
        url = org["html_url"]
        facts = PublicCompanyFacts(source=self.name, source_label=self.source_label,
                                   source_url=url, github_url=url)
        facts.field_evidence.append(CompanyFieldEvidenceRecord(
            field="github_url", value=url, source=self.source_label,
            source_type=self.source_type, source_url=url,
            evidence_text="Public GitHub organization matched by name/domain",
            source_priority=6, trust_score=80))
        return facts

    def discover_people(self, ctx: CompanyContext, roles: list[str]) -> list[PublicPerson]:
        people: list[PublicPerson] = []
        seen: set[str] = set()

        # 1) Users who publicly list this company on their profile (self-declared).
        items = self._client.search_users(f'"{ctx.company_name}" in:company type:user',
                                          per_page=_MAX_CANDIDATES)
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

        # 2) PUBLIC members of the company's official GitHub org — authoritative current
        # employees (membership is only visible when the person made it public). Stronger
        # evidence than a self-declared profile company (§4/§5).
        org = self._matched_org(ctx)
        if org and org.get("login"):
            members = self._client.get_org_public_members(org["login"], per_page=_MAX_MEMBERS)
            for m in members[:_MAX_MEMBERS]:
                login = m.get("login")
                if not login or login in seen:
                    continue
                seen.add(login)
                profile = self._client.get_user(login)
                if not isinstance(profile, dict):
                    continue
                person = self._to_person(profile, ctx)
                if person is None:
                    continue
                # Public org membership confirms the company + current employment.
                person.company_match_status = MATCH_VERIFIED
                person.is_current = True
                if not person.company_name:
                    person.company_name = org.get("name") or ctx.company_name
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
