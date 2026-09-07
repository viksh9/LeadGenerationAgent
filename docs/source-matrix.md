# Real Data Source Matrix

This is the authoritative catalogue of every candidate **real** data source for
LeadGenerationAgent, what each provides, and its **truthful** current status.

> **No source is connected yet.** A collector class existing — or even having
> credentials present — is *not* the same as an active, verified connection. A
> source is reported `CONNECTED` only **after a real live request has actually
> succeeded**. Today, none have been verified live: most sources' connection
> status is `NOT_CONFIGURED`, and the official ATS collectors (Greenhouse, Lever)
> are `DISCOVERY_REQUIRED` — implemented and working, but awaiting a legitimate
> board token / site handle before they can run. The application data mode is
> **`REAL_ONLY`**: there is no demo, mock, or synthetic runtime path.

The catalogue itself lives in [`config/sources.yaml`](../config/sources.yaml) and
is loaded as `SourceDefinition` records by
[`collectors/source_registry.py`](../collectors/source_registry.py). Runtime
status is computed by [`collectors/source_status.py`](../collectors/source_status.py)
and persisted connectivity health lives in the `source_health` table, written by
[`collectors/connectivity.py`](../collectors/connectivity.py).

## Status legend

Two independent axes are tracked and never collapsed into one:

**Implementation / configuration readiness** (`collectors/source_status.py`,
`RuntimeSourceStatus` — no network call):

| Status | Meaning |
| --- | --- |
| `IMPLEMENTED` | A collector class exists for the source. |
| `CONFIGURED` | Implemented **and** required credentials/config are present — but not yet verified against the live source. |
| `DISCOVERY_REQUIRED` | Implemented and the collector works, but the specific target (e.g. an ATS board token / site handle) is **not yet known**. Needs a legitimate board to be discovered/configured before it can run. |
| `NOT_CONFIGURED` | Implemented but missing credentials/per-source configuration. |
| `NOT_IMPLEMENTED` | No collector class exists yet (catalogued/planned only). |
| `REQUIRES_REVIEW` | Blocked pending a compliance/licensing review before it may be enabled. |

**Connection status** (`source_health` table, written only by a real probe):

| Status | Meaning |
| --- | --- |
| `CONNECTED` | A real request **actually succeeded**. Set only by a live check. |
| `DISCOVERY_REQUIRED` | Collector works but no target board/site is configured yet (official ATS sources); no live request has been attempted. |
| `NOT_CONFIGURED` | No verified live request has succeeded (missing credentials/config). |

"IMPLEMENTED" describes code; "CONFIGURED" describes credentials; "CONNECTED"
describes a verified live request. All three must be true — in that order — before
a source produces real data.

## Source summary

| Source | Provider | Category | Collector | Implementation | Connection | Evidence tier |
| --- | --- | --- | --- | --- | --- | --- |
| Adzuna Jobs API | Adzuna | JOB | `collectors/jobs/adzuna.py` | IMPLEMENTED | `NOT_CONFIGURED` | TIER_2 |
| Jooble Jobs API | Jooble | JOB | `collectors/jobs/jooble.py` | IMPLEMENTED | `NOT_CONFIGURED` | TIER_2 |
| Greenhouse Job Board API | Greenhouse (official, public) | JOB / ATS | `collectors/ats/greenhouse.py` | IMPLEMENTED | `DISCOVERY_REQUIRED` | TIER_1 |
| Lever Postings API | Lever (official, public) | JOB / ATS | `collectors/ats/lever.py` | IMPLEMENTED | `DISCOVERY_REQUIRED` | TIER_1 |
| Company Career Pages | Public web (per company) | COMPANY | `collectors/company/career_page.py` | IMPLEMENTED (per-source config; not `source_id`-runnable) | `NOT_CONFIGURED` | Not yet assigned |
| Company Newsroom / RSS | Official company feeds | NEWS | `collectors/business/collector.py` | IMPLEMENTED (per-source config; not `source_id`-runnable) | `NOT_CONFIGURED` | Not yet assigned |
| Government Procurement / Open Data | Government open-data portals | GOVERNMENT / TENDER | — | NOT_IMPLEMENTED | `NOT_CONFIGURED` | Not yet assigned |
| Project / Contract Registry | Public registries | PROJECT | — | NOT_IMPLEMENTED | `NOT_CONFIGURED` | Not yet assigned |
| Business / Company Database | Third-party (commercial) | BUSINESS_DATABASE | — | NOT_IMPLEMENTED | `NOT_CONFIGURED` | Not yet assigned |

Per-source detail follows.

---

## Adzuna Jobs API

- **Purpose**: Real IT job postings across India — the primary hiring-signal
  source for staffing/technology-service opportunities.
- **Provider**: Adzuna (job aggregator). Docs: <https://developer.adzuna.com/>.
  Official Search API reference: <https://developer.adzuna.com/docs/search>.
- **Data provided (fields)**: job title, company, location, description, salary,
  posting/created date, job id, and the source URL. Capabilities:
  `jobs, companies, job_dates, job_locations, technologies, source_urls, source_ids`.
- **Endpoint** (`collectors/jobs/client.py`):
  `GET https://api.adzuna.com/v1/api/jobs/{country}/search/{page}`
  with query params `app_id`, `app_key`, `what`, `where`, `results_per_page`,
  `max_days_old`, `sort_by=date`, `content-type=application/json`. `{country}`
  defaults to `in` (India).
- **Authentication**: API **key pair** (`API_KEY_PAIR`) sent as query params —
  `ADZUNA_APP_ID` + `ADZUNA_APP_KEY`. Read from the environment only; never logged
  or committed.
- **Query strategy** (`collectors/jobs/query_strategy.py`): a controlled strategy
  replaces the old blind `roles × locations × pages` cartesian to protect the API
  quota. `ADZUNA_SEARCH_MODE` selects the mode — `ROLE_FIRST` (default) /
  `TECHNOLOGY_FIRST` issue **one India-wide search per term** (no per-city fan-out;
  the country path already scopes to India), while `LOCATION_FIRST` issues one broad
  IT search per major Indian city. `ADZUNA_MAX_REQUESTS_PER_RUN` (default `30`) is a
  hard per-run request cap.
- **Env vars**: `ADZUNA_APP_ID`, `ADZUNA_APP_KEY`, `ADZUNA_COUNTRY` (default `in`),
  `ADZUNA_SEARCH_MODE` (default `ROLE_FIRST`), `ADZUNA_MAX_REQUESTS_PER_RUN`
  (default `30`), plus tuning knobs (`ADZUNA_API_BASE_URL`, `ADZUNA_SEARCH_TERMS`,
  `ADZUNA_LOCATIONS`, `ADZUNA_LOOKBACK_DAYS`, `ADZUNA_RESULTS_PER_PAGE`,
  `ADZUNA_MAX_PAGES`, `ADZUNA_REQUESTS_PER_MINUTE`, `ADZUNA_DAILY_REQUEST_LIMIT`,
  `ADZUNA_TIMEOUT_SECONDS`, `ADZUNA_INTEGRATION_TEST`). See
  [`.env.example`](../.env.example).
- **Capabilities**: search (`what`), location filter (`where`), pagination, date
  recency filter (`max_days_old` — a recency window, **not** a true cursor),
  salary, job id.
- **Ingestion metrics**: after a run, `GET /sources` and `GET /sources/status`
  report per-source `last_ingestion_at`, `last_ingestion_records_fetched`, and
  `last_ingestion_records_persisted` (`null` ⇒ "Not yet ingested"); the per-run
  audit (`ingestion/ingestion_audit.py`) records the full actual counts on the
  collection run. Ingestion is idempotent — re-running updates existing leads and
  skips duplicate raw records.
- **India support**: Yes. `ADZUNA_COUNTRY` defaults to `in` (India); configurable.
- **Rate limits**: Governed by your Adzuna plan; the project applies conservative
  self-limits (`ADZUNA_REQUESTS_PER_MINUTE`, `ADZUNA_DAILY_REQUEST_LIMIT`).
- **Licensing / commercial use**: `REQUIRES_APPROVAL` — commercial use requires
  review/approval per Adzuna's terms. Do **not** treat production commercial use
  as approved without confirming.
- **Implementation status**: `IMPLEMENTED` (`collectors/jobs/adzuna.py`;
  `source_id`-runnable via the CLI).
- **Connection status**: `NOT_CONFIGURED` (not verified live).
- **Evidence tier**: `TIER_2`.
- **More detail**: [`docs/sources/adzuna.md`](sources/adzuna.md).

## Jooble Jobs API

- **Purpose**: Additional real IT job postings aggregated across many job boards,
  complementing Adzuna for Indian hiring signals.
- **Provider**: Jooble. Docs:
  <https://help.jooble.org/en/support/solutions/articles/60001448238-rest-api-documentation>.
- **Data provided (fields)**: response is
  `{"totalCount": int, "jobs": [{ id, title, location, snippet, salary, source,
  type, link, company, updated }]}`. Capabilities:
  `jobs, companies, job_locations, source_urls, source_ids`.
- **Endpoint**: `POST https://{host}/api/{API_KEY}` — the key is part of the **URL
  path**. JSON body params: `keywords` (required), `location` (required),
  `radius` (optional; allowed `0, 4, 8, 16, 26, 40, 80`), `salary` (optional int),
  `page` (optional, default 1), `ResultOnPage` (optional), `SearchMode` (optional,
  default 0), `companysearch` (optional bool). Responses: `200` OK; `403` =
  invalid/missing key (auth failed); `404` not found.
- **Authentication**: single API key (`API_KEY`) in the URL path —
  `JOOBLE_API_KEY`.
- **Env vars**: `JOOBLE_API_KEY`, `JOOBLE_API_HOST` (default `jooble.org`),
  `JOOBLE_LOCATION` (default `India`), `JOOBLE_MAX_PAGES`,
  `JOOBLE_RESULTS_PER_PAGE`, `JOOBLE_REQUESTS_PER_MINUTE`,
  `JOOBLE_DAILY_REQUEST_LIMIT`, `JOOBLE_LIFETIME_REQUEST_BUDGET` (default `500`),
  `JOOBLE_TIMEOUT_SECONDS`. See [`.env.example`](../.env.example).
- **Capabilities**: keyword search, location filter, radius, salary, pagination,
  company search mode. **No** date filter and **no** true incremental cursor.
- **India support**: Yes — **but keys are per-country domain**. An India key from
  `in.jooble.org` is required for Indian listings; set
  `JOOBLE_API_HOST=in.jooble.org`.
- **Rate limits**: The FREE plan is a **hard 500-request lifetime cap per key**
  (absolute, **not** per-period). Use sparingly; the project's per-minute/daily
  knobs are conservative self-limits only.
- **Lifetime request budget (enforced)**: the app **persists request usage**
  (`source_health.requests_used` / `request_budget`) and, in `scripts/collect.py`,
  **caps a run to the remaining budget**, warns at 80% consumption, and stops
  cleanly with `BUDGET_EXHAUSTED` once the budget is used up. The ceiling is
  configurable via `JOOBLE_LIFETIME_REQUEST_BUDGET` (default `500`, matching the
  free plan).
- **Licensing / commercial use**: `REQUIRES_REVIEW` — commercial-use terms are not
  documented on the API reference page; confirm against Jooble's Terms of Service
  before commercial use.
- **Implementation status**: `IMPLEMENTED` (`collectors/jobs/jooble.py`;
  `source_id`-runnable via the CLI).
- **Connection status**: `NOT_CONFIGURED` (not verified live).
- **Evidence tier**: `TIER_2`.

## Greenhouse Job Board API

- **Purpose**: First-party IT job postings collected directly from a company's own
  Greenhouse-hosted job board — a higher-confidence, direct hiring signal than an
  aggregator's syndicated copy.
- **Provider**: Greenhouse (official public **Job Board API**). Official docs:
  <https://docs.greenhouse.io/job-board.html>.
- **Endpoint**:
  `GET https://boards-api.greenhouse.io/v1/boards/{board_token}/jobs?content=true`.
  Public — **no authentication / no key**. Implemented in
  `collectors/ats/greenhouse.py`.
- **Data provided (fields)**: response is
  `{"jobs": [{ id, title, updated_at, location:{name}, absolute_url, content,
  company_name, departments, offices }], "meta": {total}}`. Capabilities:
  `jobs, companies, job_dates, job_locations, source_urls, source_ids`.
- **Authentication**: none (public board API). Config is by **board token**, not a
  credential — `GREENHOUSE_BOARDS` (comma-separated company board tokens). Board
  tokens are format-validated; boards are **not** enumerated blindly.
- **Env vars**: `GREENHOUSE_BOARDS` (comma-separated board tokens; also settable
  per-run via `--board`). See [`.env.example`](../.env.example).
- **Capabilities**: fetch all published jobs for a board, with full posting content
  (`content=true`), locations, departments/offices, update timestamps, and the
  canonical `absolute_url`. No keyword-search API (the board returns the full list).
- **India support**: Depends on the specific board configured; Indian roles appear
  when the company's board lists them (filter downstream by `location`).
- **Rate limits**: Governed by Greenhouse; the project applies conservative
  self-limits and fetches per configured board only (no blind enumeration).
- **Licensing / commercial use**: `REQUIRES_REVIEW` — review Greenhouse's terms
  before ongoing/commercial reuse. Being publicly reachable is **not** the same as
  approved for commercial use.
- **Implementation status**: `IMPLEMENTED` (`collectors/ats/greenhouse.py`;
  `source_id`-runnable via the CLI with `--board`).
- **Connection status**: `DISCOVERY_REQUIRED` — the collector works but no board
  token is configured yet; becomes `CONNECTED` only after a real public request
  succeeds.
- **Evidence tier**: `TIER_1` (official first-party company source — higher-
  confidence direct evidence than an aggregator).
- **More detail**: [`docs/sources/greenhouse.md`](sources/greenhouse.md).

## Lever Postings API

- **Purpose**: First-party IT job postings collected directly from a company's own
  Lever-hosted board — a higher-confidence, direct hiring signal than an
  aggregator's syndicated copy.
- **Provider**: Lever (official public **Postings API**). Official docs:
  <https://github.com/lever/postings-api> (developer docs at
  <https://hire.lever.co/developer>).
- **Endpoint**:
  `GET https://api.lever.co/v0/postings/{site}?mode=json[&limit=N&skip=M]`.
  Public — **no authentication / no key**. Only **published** postings are
  returned. Implemented in `collectors/ats/lever.py`.
- **Data provided (fields)**: response is a **list** of
  `{ id, text, categories:{location, team, commitment, department}, hostedUrl,
  applyUrl, createdAt (epoch ms), descriptionPlain, workplaceType }`. Capabilities:
  `jobs, companies, job_dates, job_locations, source_urls, source_ids`.
- **Authentication**: none (public postings API). Config is by **site handle**, not
  a credential — `LEVER_SITES` (comma-separated company site handles).
- **Env vars**: `LEVER_SITES` (comma-separated site handles; also settable per-run
  via `--board`). See [`.env.example`](../.env.example).
- **Capabilities**: fetch all published postings for a site with `limit`/`skip`
  pagination, categories (location/team/commitment/department), plain-text
  description, workplace type, creation timestamp, and the canonical `hostedUrl` /
  `applyUrl`. No keyword-search API (the site returns the full list).
- **India support**: Depends on the specific site configured; Indian roles appear
  when the company's board lists them (filter downstream by `categories.location`).
- **Rate limits**: Governed by Lever; the project applies conservative self-limits
  and fetches per configured site only.
- **Licensing / commercial use**: `REQUIRES_REVIEW` — review Lever's terms before
  ongoing/commercial reuse. Being publicly reachable is **not** the same as
  approved for commercial use.
- **Implementation status**: `IMPLEMENTED` (`collectors/ats/lever.py`;
  `source_id`-runnable via the CLI with `--board`).
- **Connection status**: `DISCOVERY_REQUIRED` — the collector works but no site
  handle is configured yet; becomes `CONNECTED` only after a real public request
  succeeds.
- **Evidence tier**: `TIER_1` (official first-party company source — higher-
  confidence direct evidence than an aggregator).
- **More detail**: [`docs/sources/lever.md`](sources/lever.md).

> **Syndication is one evidence group.** One canonical job may carry **multiple**
> source references across Adzuna / Jooble / ATS. Syndicated copies of the same
> posting form a single evidence group — **not** independent confirmations.
> Discovered boards are recorded in the `company_career_sources` table
> (`CompanyCareerSource`) with status `DISCOVERY_REQUIRED` / `CONFIGURED` /
> `CONNECTED`. Both ATS collectors reuse the standard pipeline (raw → normalize →
> canonical dedup → company resolution → evidence verification → signal →
> opportunity → lead).

## Company → ATS discovery & verification

The Greenhouse and Lever collectors above run against a **known** board token / site
handle. This layer establishes *which* official ATS a company we already track
actually uses, and verifies that company-to-ATS relationship **safely** — without
guessing board ids or crawling the open web.

- **Service**: `collectors/company/career_source_discovery.py`.
- **Input**: a **real company already in the DB** that has a domain/website. Discovery
  is never run against an arbitrary URL.
- **What it probes**: **only the company's own domain and its declared careers URL**.
  The candidate URLs are deterministic — the declared `{careers_url}`,
  `https://{domain}/careers`, `https://{domain}/jobs`, and the domain root. It **never**
  fetches arbitrary third-party URLs and **never** blindly crawls the internet.
- **How it fetches**: through the existing `SafeHttpClient` — HTTPS upgrade, SSRF
  guard, private-network block, validated redirects, response-size cap, polite rate
  limiting, transient-only retries, no credentials sent or logged.
- **How a relationship is verified**: discovery detects a Greenhouse `board_token` or
  Lever site handle **found on the company's own careers page** (a link) or reached
  **via a redirect from it**, and only then marks the relationship **VERIFIED**. It
  **never** fabricates a board id. The `discovery_method` is recorded as either
  `careers_page_link` or `careers_page_redirect`.

### `company_career_sources` registry

A verified relationship is persisted in the `company_career_sources` table
(`CompanyCareerSource`): `company_id` link, `ats_provider`, `board_identifier`,
`careers_url`, `discovery_method`, and `status`. Status lifecycle:

| Status | Meaning |
| --- | --- |
| `DISCOVERY_REQUIRED` | No board/site is known for the company yet. |
| `CONFIGURED` | A relationship has been discovered and verified. |
| `CONNECTED` | A real collection/health request against that board has actually succeeded. |

Discovery and collection are **incremental and idempotent** — re-running updates the
existing relationship and skips duplicate raw records rather than creating duplicates.

### Career-source API

Implemented in `api/routes/career_sources.py`. GET endpoints make **no** network calls
and never return credentials.

| Method & path | Purpose |
| --- | --- |
| `GET /career-sources` | List all discovered/registered company career sources. |
| `GET /career-sources/{id}` | Detail for one career source. |
| `GET /companies/{id}/career-sources` | Career sources registered for one company. |
| `POST /companies/{id}/discover-career-source` | Run the real, safe own-domain discovery for a company and register any verified relationship. |
| `POST /career-sources/{id}/check` | Real connectivity health check for that board; updates `status`. |
| `POST /career-sources/{id}/collect` | Real collection for that board through the full pipeline; returns actual counts. |

### Direct-official vs aggregator evidence

An official company source is **`TIER_1`** evidence — higher-confidence **direct**
evidence than the Adzuna / Jooble aggregators (**`TIER_2`**). Official-source jobs flow
through the **same** pipeline (raw → normalize → canonical dedup → company resolution →
evidence verification → signal → opportunity → lead). One canonical job may carry
multiple source references across the official ATS + Adzuna + Jooble; syndicated copies
of the same posting are **one** evidence group — **not** independent confirmations.
Company-level intelligence therefore shows **canonical job counts, not the sum of
per-source counts**.

No unrestricted URL fetching is exposed anywhere — discovery only follows the company's
own domain, robots.txt and site terms are respected, and no credentials are logged.
Public, no-auth, board/site format-validated, IT-relevance filtered, provenance `REAL`;
commercial / ongoing reuse remains `REQUIRES_REVIEW`. More detail:
[`docs/career-source-discovery.md`](career-source-discovery.md).

## Company Career Pages

- **Purpose**: High-confidence hiring signals collected directly from a company's
  own careers/jobs pages.
- **Provider**: The company's own public web pages (per-company).
- **Data provided (fields)**: job title, location, description, posting date, and
  the source URL — sourced structured-data-first (JSON-LD / embedded JSON).
- **Authentication**: none (public pages only). No API key.
- **Env vars**: policy/safety knobs only — `CAREER_USER_AGENT`,
  `CAREER_REQUESTS_PER_MINUTE`, `CAREER_MAX_PAGES`, `CAREER_MAX_RECORDS`,
  `CAREER_MAX_RESPONSE_SIZE_MB`, `CAREER_MAX_REDIRECTS`, `CAREER_LOOKBACK_DAYS`,
  `CAREER_ALLOW_PRIVATE_HOSTS`, `CAREER_ALLOWLISTED_HOSTS`,
  `CAREER_PAGE_INTEGRATION_TEST`, `CAREER_PAGE_TEST_URL`. Per-company sources live
  in `config/career_sources.yaml`.
- **Capabilities**: pagination, location, salary, job id. No search API; no
  JavaScript execution. Robots-aware and SSRF-guarded.
- **India support**: Depends on the specific company pages configured.
- **Rate limits**: Conservative per-site self-limits (`CAREER_REQUESTS_PER_MINUTE`,
  `CAREER_MAX_PAGES`, `CAREER_MAX_RECORDS`).
- **Licensing / commercial use**: `RESTRICTED` / `REQUIRES_REVIEW` — each site's
  robots.txt and terms must be reviewed per company before enabling; collect only
  permitted public pages and store no personal data.
- **Implementation status**: `IMPLEMENTED` (`collectors/company/career_page.py`).
  Configured **per-source** in `config/career_sources.yaml`; it is **not**
  `source_id`-runnable from the generic collect CLI.
- **Connection status**: `NOT_CONFIGURED` (no reviewed/verified per-company source).
- **Evidence tier**: Not yet assigned.
- **More detail**: [`docs/sources/company-career-pages.md`](sources/company-career-pages.md).

## Company Newsroom / RSS

- **Purpose**: Business signals (expansions, delivery centers, transformation
  programs) from official company newsroom / press-release feeds — the highest
  source-confidence business signal.
- **Provider**: Official company newsroom / press-release RSS/Atom feeds
  (per-company). Also covers reviewed business/technology news RSS.
- **Data provided (fields)**: announcement title, link, summary/description, and
  published/updated dates.
- **Authentication**: none (public feeds only). No API key.
- **Env vars**: none required; feed URLs are configured per source.
- **Capabilities**: incremental fetch and date filter (feed-based). No keyword
  search API. Reads permitted RSS/Atom only.
- **India support**: Depends on the specific feeds configured.
- **Rate limits**: Conservative per-feed self-limits.
- **Licensing / commercial use**: `REQUIRES_APPROVAL` / `REQUIRES_REVIEW` — review
  each publisher's terms per feed; store links/summaries and respect publisher
  terms for full text.
- **Implementation status**: `IMPLEMENTED` (`collectors/business/collector.py`).
  Configured **per-source** (per-feed); **not** `source_id`-runnable from the
  generic collect CLI.
- **Connection status**: `NOT_CONFIGURED` (no reviewed/verified feed).
- **Evidence tier**: Not yet assigned.

## Government Procurement / Open Data

- **Purpose**: Public technology tenders/RFPs and award signals from government
  open-data / e-procurement portals. (A tender is classified first and is never
  treated as a sales opportunity on its own.)
- **Provider**: Government open-data / e-procurement portals.
- **Data provided (fields)**: tender/award records (project, dates, location) —
  fields depend on the specific portal.
- **Authentication**: typically none (open data); confirm per portal.
- **Env vars**: none defined yet.
- **Capabilities (planned)**: search, pagination, date filter, incremental fetch.
- **India support**: Target is Indian government technology tenders/RFPs.
- **Rate limits**: Per-portal; conservative defaults to be set when implemented.
- **Licensing / commercial use**: `ALLOWED` in principle (open-data licences
  usually permit reuse with attribution); verify the specific portal's licence.
- **Implementation status**: `NOT_IMPLEMENTED` (catalogued/planned; no collector).
- **Connection status**: `NOT_CONFIGURED`.
- **Evidence tier**: Not yet assigned.

## Project / Contract Registry

- **Purpose**: Awarded projects/contracts as demand signals from public registries.
- **Provider**: Candidate public open-data project/contract registries.
- **Data provided (fields)**: awarded project/contract records — fields depend on
  the specific registry.
- **Authentication**: to be determined per registry.
- **Env vars**: none defined yet.
- **Capabilities (planned)**: search, pagination, date filter, incremental fetch.
- **India support**: To be determined per registry.
- **Rate limits**: Per-registry; to be set when implemented.
- **Licensing / commercial use**: `UNKNOWN` — evaluate the licence before enabling.
- **Implementation status**: `NOT_IMPLEMENTED` (catalogued/planned; no collector).
- **Connection status**: `NOT_CONFIGURED`.
- **Evidence tier**: Not yet assigned.

## Business / Company Database (third-party)

- **Purpose**: Company-identity / firmographics enrichment to support entity
  resolution and company intelligence.
- **Provider**: A third-party commercial business/company database (candidate).
- **Data provided (fields)**: firmographics / company identity — fields depend on
  the chosen provider.
- **Authentication**: API key (required); provider-specific.
- **Env vars**: none defined yet.
- **Capabilities (planned)**: search, pagination.
- **India support**: Depends on the chosen provider.
- **Rate limits**: Per-provider plan.
- **Licensing / commercial use**: `REQUIRES_APPROVAL` — a commercial licence is
  required; review before enabling.
- **Implementation status**: `NOT_IMPLEMENTED` (catalogued/planned; no collector).
- **Connection status**: `NOT_CONFIGURED`.
- **Evidence tier**: Not yet assigned.

---

## Manual ingestion (CLIs)

Collectors run **only** when explicitly invoked — never on startup. All commands
persist **REAL** raw records with provenance; none ever insert dummy data.

```bash
# List sources whose collectors are runnable by source id.
python scripts/collect.py --list

# Run a real collection for one source and persist REAL raw records.
#   --query / --location  override the search
#   --max-pages / --per-page  bound the request plan
#   --dry-run  fetch and summarize, but persist NOTHING
python scripts/collect.py --source adzuna
python scripts/collect.py --source jooble --query "python developer" --location Bengaluru
python scripts/collect.py --source adzuna --max-pages 2 --dry-run

# Adzuna controlled query strategy + hard per-run request cap.
python scripts/collect.py --source adzuna --mode ROLE_FIRST --max-requests 30
python scripts/collect.py --source adzuna --mode LOCATION_FIRST --skip-aggregate

# Official ATS boards (public, no key). Pass a board token / site handle with
# --board, or configure defaults via GREENHOUSE_BOARDS / LEVER_SITES.
python scripts/collect.py --source greenhouse --board <board_token>
python scripts/collect.py --source lever --board <site_handle>
python scripts/collect.py --source greenhouse --board <board_token> --dry-run  # real request, persists nothing
```

`scripts/collect.py` exit codes: `0` OK · `1` error/unknown source · `2`
`NOT_CONFIGURED` (missing credentials — reported **without** any network call) ·
`3` `NOT_IMPLEMENTED` (no runnable collector for the source).

```bash
# Real connectivity check — performs a live request and persists the outcome
# to the source_health table.
python scripts/source_check.py --source adzuna
python scripts/source_check.py --source greenhouse
python scripts/source_check.py --source lever
python scripts/source_check.py --all
```

A source is reported `CONNECTED` **only** when the live request actually
succeeds; sources without credentials report `NOT_CONFIGURED` and make **no**
network call.

```bash
# Real-data-only compliance audit of the database.
python scripts/db_audit.py
```

## Source status API

All GET endpoints make **no** network calls and **never** return credentials.

| Method & path | Purpose |
| --- | --- |
| `GET /sources` | Truthful status for every catalogued source: implementation/config readiness, declared capabilities, licensing/commercial-use, the last verified connectivity check (`connection_status` + `last_checked_at` / `last_success_at` / `last_failure_at`), and per-source **ingestion metrics** (`last_ingestion_at`, `last_ingestion_records_fetched`, `last_ingestion_records_persisted`; `null` ⇒ "Not yet ingested"). |
| `GET /sources/status` | Alias of `GET /sources` — same truthful payload (incl. ingestion metrics). |
| `POST /sources/{id}/check` | Perform a real, credential-based connectivity check on demand and persist the outcome. Sources without credentials return `NOT_CONFIGURED` and make no network call. |

A source becomes `CONNECTED` in these responses only after a verified live request
has succeeded.

## Testing / live integration tests

- The default test suite (`pytest`) makes **no external network calls** — every
  HTTP interaction is served by mocks/fixtures, and no credentials are required.
- Live integration tests are **opt-in** via `RUN_LIVE_SOURCE_TESTS=true` **plus**
  the relevant per-source credentials. Individual live smoke tests are additionally
  gated by their own per-source flags (for example `ADZUNA_INTEGRATION_TEST=true`,
  `CAREER_PAGE_INTEGRATION_TEST=true` with `CAREER_PAGE_TEST_URL`).
- Live tests make minimal calls (e.g. a single `results_per_page=1` request) and
  are skipped entirely unless explicitly enabled.

## Data provenance

Every real record carries `data_provenance = REAL` and traces back to a source
(URL / name / evidence). The application data mode is **`REAL_ONLY`** — there is
no demo/mock/synthetic runtime path. Write guards in
[`database/integrity.py`](../database/integrity.py) reject `SYNTHETIC` records and
`REAL` leads that carry no source-backed evidence; generated AI text never counts
as evidence. `python scripts/db_audit.py` is the operational check that the
database remains real-data-only. An empty database is a valid, correct state.
