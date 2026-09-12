"""Official company website provider.

Wraps the existing OfficialCompanySourceEnricher (enrichment/person_enricher.py),
which already fetches only publicly-accessible company pages (/about, /team,
/leadership, /contact, …) via the SSRF-safe, robots-respecting SafeHttpClient,
extracts schema.org Person entities (JSON-LD), and collects ONLY published
`mailto:` business emails (never guessed). We normalize its output to PublicPerson /
PublicContact. People from the company's OWN site are current-company by definition.
"""

from __future__ import annotations

from typing import Optional

from enrichment.person_enricher import OfficialCompanySourceEnricher
from integrations.public_intelligence.base import PublicIntelligenceProvider
from integrations.public_intelligence.models import (
    MATCH_VERIFIED,
    CompanyContext,
    PublicContact,
    PublicPerson,
)


class OfficialCompanyProvider(PublicIntelligenceProvider):
    name = "official_company"
    source_label = "Official Company Website"
    source_type = "company_profile"

    def __init__(self, enricher: Optional[OfficialCompanySourceEnricher] = None) -> None:
        self._enricher = enricher or OfficialCompanySourceEnricher()

    def _run(self, ctx: CompanyContext):
        if not (ctx.domain or ctx.website):
            return None
        return self._enricher.enrich(company_name=ctx.company_name, domain=ctx.domain, website=ctx.website)

    def discover_people(self, ctx: CompanyContext, roles: list[str]) -> list[PublicPerson]:
        result = self._run(ctx)
        if result is None:
            return []
        people: list[PublicPerson] = []
        for p in result.people:
            people.append(PublicPerson(
                full_name=p.get("full_name"),
                job_title=p.get("job_title"),
                department=p.get("department"),
                seniority=p.get("seniority"),
                company_name=ctx.company_name,
                company_domain=ctx.domain,
                linkedin_url=None,   # the enricher stores profile_url on its own site, not LinkedIn
                location=None,
                is_current=True,     # published on the company's OWN site
                company_match_status=MATCH_VERIFIED,
                source=self.name, source_label=self.source_label, source_type=self.source_type,
                source_url=p.get("source_url"),
                source_record_id=p.get("profile_url") or p.get("source_url"),
            ))
        return people

    def discover_public_contacts(self, ctx: CompanyContext) -> list[PublicContact]:
        result = self._run(ctx)
        if result is None:
            return []
        contacts: list[PublicContact] = []
        for c in result.contacts:
            contacts.append(PublicContact(
                kind="BUSINESS_EMAIL", value=c.get("business_email"),
                source=self.name, source_label=self.source_label, source_type=self.source_type,
                source_url=c.get("source_url"),
            ))
        return [c for c in contacts if c.value]

    def discover(self, ctx: CompanyContext, roles: list[str]):
        # Single fetch reused for both people + contacts (the enricher caches pages).
        return super().discover(ctx, roles)
