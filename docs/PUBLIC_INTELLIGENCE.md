# Free/Public Intelligence Layer

Discovers legitimately **public** company and POC information from **free** sources —
no paid contact-data providers, no guessed emails/phones, no fabricated people. Every
fact carries provenance; a provider failure never yields fake data (§29).

## Architecture (provider-based)

`integrations/public_intelligence/` — decoupled providers behind a common interface:

```
base.py          PublicIntelligenceProvider (discover_company / discover_people /
                 discover_public_contacts / health_check) → normalized ProviderResult
models.py        CompanyContext, PublicPerson, PublicContact, PublicCompanyFacts,
                 FieldProvenance, status/match constants, SOURCE_PRIORITY
registry.py      free-first registry — per-provider enable/disable
http.py          shared GET JSON client (rate limit, retry/backoff, Retry-After)
matching.py      company match (VERIFIED/LIKELY/UNKNOWN) + role relevance
trust.py         public Contact Trust (§19) + POC status (§22)
official_company/  wraps the existing SSRF-safe, robots-respecting company enricher
github/            GitHub public REST API (anonymous; optional token)
wikidata/          Wikidata public SPARQL (company identity)
public_registry/   extensible abstraction only (no bundled registry)
rss/               RSS/Atom collector abstraction (configured feeds only)
```

Orchestration lives in `enrichment/public_intelligence_service.py`; POCs persist as
`DecisionMaker` rows (reusing the existing model + resolution), so the Lead Details
Target POC panel and the 16-column Excel export surface them automatically.

## Providers & source APIs

| Provider | Source | Public API | Use |
|---|---|---|---|
| official_company | Official company website | `/about`, `/team`, `/leadership`, `/contact` (SSRF-safe, robots-respecting) | People (JSON-LD Person) + published `mailto:` business emails |
| github | GitHub | `GET /search/users`, `GET /users/{login}`, `GET /orgs/{login}` | Technical POC candidates; public email ONLY if returned |
| wikidata | Wikidata | `query.wikidata.org/sparql` | Company identity: website, country, industry, `wikidata_id` |
| public_registry | — | abstraction only (§15) | Pluggable; no bundled registry |
| rss | Configured feeds | RSS/Atom | Announcement abstraction (no POCs) |

## Company resolution & POC discovery

The lead resolves to its canonical `Company` by normalized name. Recommended POC roles
come from the existing opportunity→role engine (`enrichment/poc_finder.py`). Each
enabled provider discovers people/contacts/company facts; people are merged across
sources by strong identifiers (LinkedIn → email → provider id → name+company, §21) and
a person is attached only when company association is at least LIKELY (§9). Roles with
no matched person remain `RECOMMENDED_ROLE_ONLY` (never a fabricated person).

## Public email / phone rules

- **Email** is accepted ONLY when explicitly published (company page `mailto:`, or a
  GitHub-returned public `email`). Naming conventions are never used to guess an
  address (§6). A personal email is never presented as the business contact.
- **Phone** is accepted ONLY when explicitly published; a company switchboard is stored
  as a company phone, never a person's phone (§7). Numbers are never inferred.
- **LinkedIn** URLs are stored verbatim (§13); never scraped, never constructed.

## Contact Trust (§19) — separate from Lead Score (§31)

`integrations/public_intelligence/trust.py`, max 100:
official source **+35**, current company match **+25**, current title match **+20**,
explicit public business email **+10**, explicit public business phone **+10**. Points
are awarded only on real evidence — 100% requires every criterion. POC status: VERIFIED
/ LIKELY / RECOMMENDED_ROLE_ONLY / UNVERIFIED / STALE.

## Provenance & source priority

Field-level provenance (§18) is stored in `DecisionMaker.source_references`; each
person carries `contact_source` (label), `source_type`, `source_url`,
`source_record_id`, `last_verified_at`, `data_provenance=REAL`. When the same fact
appears in multiple sources the higher-priority source is canonical (official company >
official ATS > GitHub > Wikidata), and corroborating sources are retained — never
silently overwritten (§20).

## Caching, rate limiting, observability

Recent public POCs are reused within `PUBLIC_INTELLIGENCE_CACHE_TTL_HOURS` (default 168)
instead of re-fetching. Each network provider has its own rate limit
(`GITHUB_RATE_PER_MINUTE`, `WIKIDATA_RATE_PER_MINUTE`) with bounded retry/backoff
honouring `Retry-After` (429/5xx/timeout handled). Structured logs:
`public_intelligence.request/success/empty/error/rate_limited`.

## API endpoints

- `POST /leads/{id}/public-intelligence/discover` (SALES, rate-limited)
- `GET /companies/{id}/public-intelligence` — company facts + public leadership
- `GET /leads/{id}/pocs` — all POCs (public + ContactOut) + role recommendations
- `POST /public-intelligence/test?provider=wikidata` — real connectivity check →
  `LIVE_VERIFIED` / `NOT_CONFIGURED` / `SOURCE_UNAVAILABLE` / `ERROR` (never claims
  LIVE_VERIFIED without a real request).

## Excel export

Unchanged **16 columns**. Target POC Details shows the real person(s) (`Name — Role`,
up to two) or the role-only recommendation; Contact Number / Email carry the public
business phone / work email or stay blank; the **Source** column names the actual public
source(s) (Official Company Website / GitHub / ContactOut).

## Configuration

`PUBLIC_INTELLIGENCE_ENABLED` (master, default on) + `OFFICIAL_COMPANY_INTELLIGENCE_ENABLED`
/ `GITHUB_INTELLIGENCE_ENABLED` / `WIKIDATA_INTELLIGENCE_ENABLED`
/ `PUBLIC_REGISTRY_INTELLIGENCE_ENABLED` / `RSS_INTELLIGENCE_ENABLED`. Optional
`GITHUB_API_TOKEN` (never required, never exposed), `PUBLIC_INTELLIGENCE_USER_AGENT`,
`RSS_INTELLIGENCE_FEEDS`, per-provider rate limits, timeout, and cache TTL.

## Privacy & no-fabrication

Only legitimately-public information is collected; no passwords/tokens/private
contacts/hidden APIs; robots and site terms are respected. If GitHub/Wikidata/website
fail or return nothing, the field stays unavailable and role recommendations are shown
— never invented people/emails/phones (§29/§32).

## Testing

Offline (mocked transports): `tests/unit/test_public_intelligence.py`,
`tests/integration/test_public_intelligence_service.py`,
`tests/integration/test_public_intelligence_api.py`, + the public-source Excel case in
`tests/integration/test_export.py`. Frontend: the Target POC panel test.
