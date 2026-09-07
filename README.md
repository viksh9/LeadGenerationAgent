# LeadGenerationAgent

A **real-data-only** B2B sales-intelligence platform for the **Indian IT industry**.
It converts real technology hiring and business signals — collected from permitted
sources — into qualified IT-staffing and technology-service opportunities: company
intelligence, verified signals, decision-maker role recommendations, and scored leads.

## Real-data-only policy

This application contains **no demo, dummy, mock, fake, synthetic, sample,
placeholder, or seeded business data** in any runtime path. Every company, job,
lead, signal, and opportunity shown in the dashboard/APIs is derived from data
actually collected from a permitted real source and stored with provenance.

What this means in practice:

- **An empty database is a valid, correct state.** With no collected data the
  dashboard, companies, leads, and opportunities pages show honest empty states
  ("No verified real data available yet") — never fabricated numbers.
- **Startup never seeds business data.** `init_db()` only creates schema/indexes.
- **Provenance is mandatory.** Every business record carries `data_provenance`
  (`REAL`), and real records trace back to a source (URL/name/evidence).
- **Write guards.** In production/staging the write layer rejects `SYNTHETIC`
  records and `REAL` leads that carry no source-backed evidence
  (`database/integrity.py`). Generated AI text never counts as evidence.
- **Synthetic data is test-only.** Minimal synthetic fixtures live *inside the
  test suite* (`tests/fixtures/`), run against isolated throwaway databases, and
  are never loaded into the application database or used as UI fallback.

Nothing here claims a real source is "connected" unless a collector has actually
been implemented, configured, and verified against the live source. See
[Current source integration status](#current-source-integration-status).

## Architecture — the real-data flow

Every stage preserves provenance:

```
REAL SOURCE
  → COLLECTOR            collectors/            (Adzuna API, career pages, RSS…)
  → RAW SOURCE RECORD    raw_source_records     (immutable, original payload)
  → NORMALIZATION        processors/normalization, ingestion/
  → DEDUPLICATION        processors/deduplication  (count each real job once)
  → COMPANY RESOLUTION   company/                  (deterministic, no fuzzy merge)
  → EVIDENCE VERIFICATION verification/            (source reliability, freshness…)
  → SIGNAL DETECTION     intelligence/
  → OPPORTUNITY ANALYSIS intelligence/
  → LEAD SCORING         intelligence/lead_pipeline.py
  → COMPANY / LEAD INTELLIGENCE  company/intelligence.py
  → DASHBOARD            api/ + frontend/
```

Verification keeps four distinct numbers (never collapsed into one): **source
reliability**, **evidence confidence**, **signal confidence**, and the commercial
**lead score**.

## Requirements

- Python 3.11+ · FastAPI · Pydantic v2 · SQLAlchemy 2.x · SQLite · Uvicorn · pytest
- Node 18+ for the React frontend

## Layout

```
LeadGenerationAgent
├── api/            # FastAPI app + routes (health, leads, companies, sources)
├── collectors/     # Real-source collectors + source registry & status
├── ingestion/      # Normalization + dedup + company pipelines
├── processors/     # Normalization & deduplication engines
├── company/        # Entity resolution + company intelligence
├── verification/   # Evidence verification & source confidence
├── intelligence/   # Signal detection, opportunity analysis, lead scoring
├── enrichment/     # Decision-maker role recommendation (roles only)
├── outreach/       # Deterministic pitch generation
├── database/       # Models, repository, session, integrity (audit + guards)
├── config/         # Settings, source catalogue (sources.yaml), policy config
├── scripts/        # Operational runners: db_audit, build_company_leads, process_raw
├── frontend/       # React 18 + TS + Vite SPA
├── tests/          # unit + integration (synthetic fixtures live here only)
└── data/           # Local SQLite db (gitignored) — no sample business data
```

## Setup

```bash
python3.11 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

## Environment configuration

Configuration is environment-based (`.env` or process env). **Credentials only
ever come from the environment — never hard-coded or committed.** `.env.example`
holds placeholders only.

| Variable | Purpose | Default |
| --- | --- | --- |
| `APP_ENV` | `development`, `staging`, or `production` | `development` |
| `DATABASE_URL` | SQLAlchemy URL (SQLite by default) | `sqlite:///./data/leads.db` |
| `ENFORCE_REAL_DATA` | Force write-guards on/off. Unset ⇒ on in production/staging | *(derived)* |
| `SHOW_SYNTHETIC_LEADS` | Show synthetic leads (dev only). Unset ⇒ off in production | *(derived)* |
| `API_HOST` / `API_PORT` | API bind address | `127.0.0.1` / `8000` |
| `CORS_ORIGINS` | Comma-separated allowed origins | local dev servers |
| `ADZUNA_APP_ID` / `ADZUNA_APP_KEY` | Adzuna jobs API credentials (optional; env only, never logged/committed) | — |
| `ADZUNA_COUNTRY` | Adzuna country code | `in` |
| `ADZUNA_SEARCH_MODE` | Query strategy: `ROLE_FIRST`, `TECHNOLOGY_FIRST`, or `LOCATION_FIRST` | `ROLE_FIRST` |
| `ADZUNA_MAX_REQUESTS_PER_RUN` | Hard cap on API requests per collection run | `30` |
| `JOOBLE_API_KEY` | Jooble jobs API key (optional; per-country key) | — |
| `JOOBLE_API_HOST` | Jooble host — use `in.jooble.org` for India | `jooble.org` |
| `JOOBLE_LIFETIME_REQUEST_BUDGET` | Hard **lifetime** request cap per Jooble key (free plan is 500 total, not per period) | `500` |
| `GREENHOUSE_BOARDS` | Comma-separated Greenhouse board tokens to collect (no key; public Job Board API) | — |
| `LEVER_SITES` | Comma-separated Lever site handles to collect (no key; public Postings API) | — |
| `OPENAI_API_KEY` / `OPENAI_MODEL` | Reserved for a later outreach phase | — |

See `.env.example` for the full list (Adzuna, Jooble, and career-page collector
knobs) and [docs/source-matrix.md](docs/source-matrix.md) for per-source detail.

## Database setup

Schema is created automatically on API startup (or `init_db()`), and **no
business data is inserted**. To inspect or clean the database:

```bash
python scripts/db_audit.py                      # real-data-only compliance report
python scripts/db_audit.py --json               # machine-readable
python scripts/db_audit.py --fail-on-synthetic  # exit 1 if any synthetic/no-provenance rows
python scripts/db_audit.py --purge-synthetic --yes   # remove synthetic rows (dev/test only)
```

The audit reports per-table totals, provenance breakdown, records missing
provenance, and REAL records missing a source URL.

## Running collectors

Collectors only run when explicitly invoked and configured — never on startup,
and never with unauthorized scraping (robots.txt, ToS, rate limits, and auth are
respected; no login/CAPTCHA/paywall bypass). Once real raw records have been
collected, aggregate them into company-level leads:

```bash
python scripts/process_raw.py            # normalize pending raw records → leads
python scripts/build_company_leads.py    # REAL raw jobs → canonical jobs → company leads
```

If nothing has been collected yet, these create no leads (honest empty state).

## Running the backend

```bash
uvicorn api.main:app --reload            # http://127.0.0.1:8000  (docs at /docs)
```

### Endpoints (selected)

| Method & path | Purpose |
| --- | --- |
| `GET /health` | Liveness |
| `GET /sources` | **Truthful** real-source connectivity status (never "Connected" without a verified live check) |
| `GET /leads` | List leads (filters, search, sort, pagination) — empty when no real data |
| `POST /leads/analyze` | Run the analysis pipeline and persist a lead |
| `GET /companies` | Company intelligence list — empty when no real data |
| `GET /leads/{id}/verification` | Four-score verification detail + evidence |

## Running the frontend

```bash
cd frontend
npm install
cp .env.example .env      # VITE_API_BASE_URL=http://localhost:8000
npm run dev               # http://localhost:5173
npm run build             # type-check + production build
npm run test              # Vitest
```

Every production screen renders API data with proper loading, error, and empty
states. On an API failure the UI shows an error state — it **never** substitutes
fake data. Settings → Data sources shows the live `/sources` status.

## Testing

```bash
pytest                                   # backend (isolated throwaway SQLite DBs)
python scripts/db_audit.py --fail-on-synthetic   # integrity gate
cd frontend && npm run test              # frontend
```

Tests never touch the development/production database. Synthetic fixtures are
confined to `tests/fixtures/` and isolated per-test databases.

## Data provenance

`data_provenance` is `REAL` for all production records. `SYNTHETIC` exists only
for test fixtures and is rejected by the production write-guards. The audit
(`database/integrity.py`, `scripts/db_audit.py`) is the operational check that the
database remains real-data-only; the data-integrity tests
(`tests/integration/test_real_data_integrity.py`) enforce it in CI.

## Current source integration status

**No external source is connected yet.** Collectors exist for some sources but a
collector class is *not* the same as an active, verified real-data connection.
`GET /sources` reports the live truth; current summary:

| Source | Collector | Status | Notes |
| --- | --- | --- | --- |
| Adzuna Jobs API | implemented | `NOT_CONFIGURED` | Set `ADZUNA_APP_ID`/`ADZUNA_APP_KEY`; verify live before use. Commercial use `REQUIRES_APPROVAL` |
| Jooble Jobs API | implemented | `NOT_CONFIGURED` | Set `JOOBLE_API_KEY` (+ `JOOBLE_API_HOST=in.jooble.org` for India); verify live before use. Free plan = 500-request **lifetime** cap per key |
| Greenhouse Job Board API | implemented | `DISCOVERY_REQUIRED` | Official public board API, no auth. Set `GREENHOUSE_BOARDS` (board tokens) or pass `--board`; `TIER_1` evidence. Commercial reuse `REQUIRES_REVIEW` |
| Lever Postings API | implemented | `DISCOVERY_REQUIRED` | Official public postings API, no auth. Set `LEVER_SITES` (site handles) or pass `--board`; `TIER_1` evidence. Commercial reuse `REQUIRES_REVIEW` |
| Company career pages | implemented | `REQUIRES_REVIEW` | Robots/ToS review per site before enabling |
| Company newsroom (RSS) | implemented | `REQUIRES_REVIEW` | Per-feed review before enabling |
| RSS business/tech news | implemented | `NOT_CONFIGURED` | No reviewed feeds configured |
| Government procurement (CPPP / GeM) | manual only | `PLANNED` / `MANUAL_SOURCE_REQUIRED` | No documented public API; no scraping. Tenders enter via the manual import CLI only. Commercial use `REQUIRES_REVIEW` |
| data.gov.in open data (OGD API) | adapter (per-dataset) | `NOT_CONFIGURED` | Legitimate open-data API under GODL. Needs `DATA_GOV_IN_API_KEY` + `DATA_GOV_IN_TENDER_RESOURCE_ID`; per-dataset field mapping. Commercial use `REQUIRES_REVIEW` |
| Project / contract registry | planned | `PLANNED` | No collector yet |
| Business database (3rd-party) | planned | `PLANNED` | Requires commercial licence |

Actual real-source ingestion (authenticating, querying, and persisting real
records) is the focus of the next phase.

## Source status & ingestion

The full catalogue — every candidate real source, its fields, authentication,
capabilities, India support, rate limits, licensing, and truthful status — is
documented in **[docs/source-matrix.md](docs/source-matrix.md)**. The application
data mode is **`REAL_ONLY`**: there is no demo/mock/synthetic runtime path, and no
source is reported `CONNECTED` until a real live request has actually succeeded.

**Manual ingestion (CLIs).** Collectors run only when explicitly invoked; they
persist only REAL records:

```bash
python scripts/collect.py --list                         # runnable sources
python scripts/collect.py --source adzuna                # real collection
python scripts/collect.py --source jooble --query "python developer" --location Bengaluru
python scripts/collect.py --source greenhouse --board <board_token>   # official ATS (public, no key)
python scripts/collect.py --source lever --board <site_handle>        # official ATS (public, no key)
python scripts/collect.py --source adzuna --max-pages 2 --dry-run   # persist nothing
python scripts/source_check.py --source adzuna           # real connectivity check → source_health
python scripts/source_check.py --all
```

`collect.py` exit codes: `0` OK · `2` `NOT_CONFIGURED` (missing credentials, no
network call) · `3` `NOT_IMPLEMENTED` (no runnable collector).

### Adzuna real-data ingestion

Adzuna is the primary hiring-signal source for Indian IT. Official API reference:
<https://developer.adzuna.com/docs/search>.

- **Endpoint** (`collectors/jobs/client.py`):
  `GET https://api.adzuna.com/v1/api/jobs/{country}/search/{page}` with query params
  `app_id`, `app_key`, `what`, `where`, `results_per_page`, `max_days_old`,
  `sort_by=date`, `content-type=application/json`. `{country}` defaults to `in`
  (India). Auth = `ADZUNA_APP_ID` + `ADZUNA_APP_KEY`, read from the environment
  only — never logged or committed.
- **Controlled query strategy** (`collectors/jobs/query_strategy.py`) — replaces the
  old blind `roles × locations × pages` cartesian to protect the API quota.
  Configured by `ADZUNA_SEARCH_MODE`:
  - `ROLE_FIRST` (default) / `TECHNOLOGY_FIRST` — issue **one India-wide search per
    term** (no per-city fan-out; the country path already scopes to India).
  - `LOCATION_FIRST` — issue one broad IT search per major Indian city.

  `ADZUNA_MAX_REQUESTS_PER_RUN` (default `30`) is a hard per-run request cap.
  Keywords are configurable via `ADZUNA_SEARCH_TERMS`, cities via
  `ADZUNA_LOCATIONS`, and pagination via `ADZUNA_MAX_PAGES`.
- **CLI**:

  ```bash
  python scripts/collect.py --source adzuna \
      [--mode ROLE_FIRST|TECHNOLOGY_FIRST|LOCATION_FIRST] \
      [--max-requests N] [--max-pages N] [--query Q --location L] \
      [--dry-run] [--skip-aggregate]
  ```

  `--dry-run` performs the **real** API request and validates/reports counts but
  persists nothing.
- **Per-run ingestion audit** (`ingestion/ingestion_audit.py`). After a run,
  `collect.py` prints and persists (on the collection run record) the **actual**
  counts: requests, raw fetched, raw persisted (new), duplicates skipped, canonical
  jobs created/updated, companies aggregated, leads created/updated, companies with
  a hiring signal, opportunities (evidence-backed), plus DB totals. Ingestion is
  **idempotent** — re-running updates existing leads and skips duplicate raw records
  rather than creating duplicates.
- **Full pipeline (reused):** Adzuna API → `RawSourceRecord` (provenance `REAL`,
  `source_url` + Adzuna id preserved) → normalization → canonical job dedup →
  company resolution → evidence verification (four distinct scores; Adzuna jobs come
  out `PARTIALLY_VERIFIED` with `source_reliability ≈ 72` for TIER_2) → signal
  detection → company-level aggregation (observed openings vs estimated need kept
  distinct) → opportunity → lead scoring → dashboard. **One company = one lead**
  (not one-per-job).
- **Licensing:** Adzuna commercial use **`REQUIRES_APPROVAL`** per their terms.
  Being technically connectable is **not** the same as approved for commercial use —
  do not treat production commercial use as approved.

### Official ATS sources (Greenhouse, Lever)

Alongside the aggregators, the platform collects directly from two **official,
public ATS APIs**. These are first-party company job boards (no auth, no key), so
their postings are treated as **`TIER_1`** evidence — higher-confidence direct
evidence than an aggregator's syndicated copy. Both reuse the standard pipeline
(raw → normalize → canonical dedup → company resolution → evidence verification →
signal → opportunity → lead).

- **Greenhouse — Job Board API** (`collectors/ats/greenhouse.py`). Official docs:
  <https://docs.greenhouse.io/job-board.html>.
  - **Endpoint**: `GET https://boards-api.greenhouse.io/v1/boards/{board_token}/jobs?content=true`.
    Public, **no authentication**. Response: `{jobs:[{id, title, updated_at,
    location:{name}, absolute_url, content, company_name, departments, offices}],
    meta:{total}}`.
  - **Config**: `GREENHOUSE_BOARDS` — comma-separated company **board tokens**; no
    key. Board tokens are format-validated; boards are **not** enumerated blindly.
- **Lever — Postings API** (`collectors/ats/lever.py`). Official docs:
  <https://github.com/lever/postings-api> (developer docs at
  <https://hire.lever.co/developer>).
  - **Endpoint**: `GET https://api.lever.co/v0/postings/{site}?mode=json[&limit=N&skip=M]`.
    Public, **no authentication**; only **published** postings are returned.
    Response: a list of `{id, text, categories:{location, team, commitment,
    department}, hostedUrl, applyUrl, createdAt (epoch ms), descriptionPlain,
    workplaceType}`.
  - **Config**: `LEVER_SITES` — comma-separated company **site handles**; no key.
- **CLI**:

  ```bash
  python scripts/collect.py --source greenhouse --board <board_token>
  python scripts/collect.py --source lever --board <site_handle>
  # or configure default boards via GREENHOUSE_BOARDS / LEVER_SITES
  python scripts/collect.py --source greenhouse --board <board_token> --dry-run  # real request, persists nothing
  python scripts/source_check.py --source greenhouse    # connectivity check
  python scripts/source_check.py --source lever
  ```

- **Syndication is one evidence group.** One canonical job may carry **multiple**
  source references across Adzuna / Jooble / ATS. Syndicated copies of the same
  posting are a single evidence group — **not** independent confirmations. Discovered
  boards are recorded in the `company_career_sources` table (`CompanyCareerSource`)
  with status `DISCOVERY_REQUIRED` / `CONFIGURED` / `CONNECTED`.
- **Status**: `DISCOVERY_REQUIRED` — the collector is implemented and works, but no
  board token / site handle is known yet. A source becomes `CONNECTED` only after a
  real public request has actually succeeded.
- **Licensing:** commercial / ongoing reuse is **`REQUIRES_REVIEW`** — review the
  Greenhouse and Lever terms before enabling ongoing commercial use. Being publicly
  reachable is **not** the same as approved for commercial reuse.

### Company → ATS source discovery

The Greenhouse and Lever collectors above run against a **known** board token /
site handle. The discovery layer answers the prior question — *which* official ATS
(if any) a company we already track actually uses — and does so **safely**, without
guessing board ids or crawling the open web.

- **Own-domain-only, deterministic probing** (`collectors/company/career_source_discovery.py`).
  Given a **real company already in the DB** (one that has a domain/website), the
  service probes **only that company's own domain and its declared careers URL**. The
  candidate URLs are deterministic: the declared `{careers_url}`, `https://{domain}/careers`,
  `https://{domain}/jobs`, and the domain root. It **never** fetches arbitrary
  third-party URLs and **never** blindly crawls the internet.
- **Safe fetching.** All requests go through the existing `SafeHttpClient` — HTTPS
  upgrade, SSRF guard, private-network block, validated redirects, response-size cap,
  polite rate limiting, transient-only retries, and no credentials sent or logged.
- **Verified relationship, never fabricated.** Discovery detects a Greenhouse
  `board_token` or Lever site handle **found on the company's own careers page** (a
  link) or reached **via a redirect from it**, and only then marks the relationship
  **VERIFIED**. It **never** fabricates a board id. The `discovery_method` is recorded
  as either `careers_page_link` or `careers_page_redirect`.
- **Persistence & status lifecycle.** A verified relationship is stored in the
  `company_career_sources` table (`CompanyCareerSource`) — `company_id`, `ats_provider`,
  `board_identifier`, `careers_url`, `discovery_method`, `status`. The status lifecycle is:
  - `DISCOVERY_REQUIRED` — no board/site is known for the company yet.
  - `CONFIGURED` — a relationship has been discovered and verified.
  - `CONNECTED` — a real collection/health request against that board has actually
    succeeded.
- **Evidence tier.** An official company source is `TIER_1` evidence — higher-confidence
  **direct** evidence than the Adzuna / Jooble aggregators (`TIER_2`).

New API endpoints (`api/routes/career_sources.py`):

| Method & path | Purpose |
| --- | --- |
| `GET /career-sources` | List all discovered/registered company career sources |
| `GET /career-sources/{id}` | Detail for one career source |
| `GET /companies/{id}/career-sources` | Career sources registered for one company |
| `POST /companies/{id}/discover-career-source` | Run the real, safe own-domain discovery for a company and register any verified relationship |
| `POST /career-sources/{id}/check` | Real connectivity health check for that board → updates `status` |
| `POST /career-sources/{id}/collect` | Real collection for that board → full pipeline → returns actual counts |

Discovery and collection are **incremental and idempotent** — re-running updates the
existing relationship and skips duplicate raw records rather than creating duplicates.

**Direct-official vs aggregator evidence.** Official-source jobs flow through the
**same** pipeline as everything else (raw → normalize → canonical dedup → company
resolution → evidence verification → signal → opportunity → lead). One canonical job
may carry **multiple** source references across the official ATS + Adzuna + Jooble.
Syndicated copies of the same posting are **one** evidence group — **not** independent
confirmations. Company-level intelligence therefore shows **canonical job counts, not
the sum of per-source counts**.

Discovery only follows the company's own domain — **no unrestricted URL fetching is
exposed anywhere**. robots.txt and site terms are respected, and no credentials are
logged. Public, no-auth, board/site format-validated, IT-relevance filtered,
provenance `REAL`; commercial / ongoing reuse remains `REQUIRES_REVIEW`.

## Decision-maker & contact enrichment

This layer answers *"who should we talk to at this company, and do we have a real,
verified way to reach them?"* — while keeping **three distinct concepts separate**
and never confusing one for another:

1. **Recommended stakeholder ROLE (no person).** A role *type* likely to own the
   decision (e.g. "VP Engineering"), driven by opportunity / signal / hiring /
   industry evidence. Deterministic and **always available** — no person is
   claimed, no network is touched.
2. **Verified real PERSON.** A named individual **only** when found in a permitted,
   traceable source. Absent that, this stays **NULL** — a person is *never*
   assumed, guessed, or fabricated.
3. **Verified business CONTACT.** A *published business* email/contact (e.g. a
   role-based address), never a personal or guessed one.

> **Role recommendation ≠ person identification ≠ contact verification ≠ outreach
> permission.** These are four separate questions with four separate answers.

Full detail: [docs/decision-maker-enrichment.md](docs/decision-maker-enrichment.md).

### Role recommendation (roles only)

The role engine (`enrichment/poc_finder.py`, wrapped by
`enrichment/stakeholder.py`) recommends decision-maker **role types** from the
detected signals, opportunity analysis, hiring, and industry — each with a
category, a relevance score, and a grounded reason. It produces **no person, no
email, no profile, and touches no network**. See also
[docs/poc-intelligence.md](docs/poc-intelligence.md).

### Official-source person / contact enricher

`enrichment/person_enricher.py` (`OfficialCompanySourceEnricher`) enriches a
company **only from that company's own official pages** — `/`, `/about`,
`/leadership`, `/team`, `/management`, `/contact` — fetched through the existing
`SafeHttpClient` (HTTPS, SSRF guard, private-network block, response-size cap, no
credentials). From that server HTML it extracts:

- **Real people** from schema.org JSON-LD `Person` entries (name + jobTitle).
- **Real business contacts** from published `mailto:` addresses that are
  role-based (`info@`, `sales@`, `careers@`, `procurement@`, …) or on the
  company's own domain.

It **never** fabricates a person, email, phone, or profile; **never** guesses
`firstname.lastname@` addresses; **never** constructs LinkedIn/profile URLs from a
name; and **never** scrapes third-party or private profiles or bypasses
auth/robots. Personal-looking addresses (e.g. a random Gmail) are rejected. When
the official pages publish nothing extractable, the result is honestly **empty /
NULL** — real careers and leadership pages are frequently JS-rendered SPAs whose
people are not in the server HTML, and there is **no browser automation** by
policy, so people are found only when published as JSON-LD.

### Distinct confidence axes, verification & freshness

Persistence and resolution live in `enrichment/enrichment_service.py`, which
stores `DecisionMaker` rows with **distinct confidence axes — never collapsed into
one**: `identity_confidence`, `role_confidence`, `company_confidence`,
`contact_confidence`, and `evidence_confidence`. Each row also carries a
`verification_status` (`VERIFIED` / `PARTIALLY_VERIFIED` / `UNVERIFIED` / `STALE`
/ `CONTRADICTED`), a `freshness_score`, and `provenance = REAL`.

- **Deterministic person resolution.** Name alone **never** merges two distinct
  people; the same person observed under a different role becomes
  `REVIEW_REQUIRED`. Upserts are idempotent, corroborating sources are kept in
  `source_references`, and history is preserved.
- **Freshness.** Reuses `verification.freshness` — a person or contact is **not**
  assumed current forever.
- **Evidence tier.** An official company source is `TIER_1` — stronger than
  aggregators.

### Outreach readiness (separate from lead score)

`enrichment/outreach.py` computes a deterministic readiness state — `READY` /
`ROLE_ONLY` / `RESEARCH_REQUIRED` / `HOLD` — that is **separate from**
`lead_score`, `evidence_confidence`, and `contact_confidence`. A recommended role
alone is **never** `READY` (that is `ROLE_ONLY`); anything stale or contradicted
is `HOLD`.

### Provider architecture

Enrichers are pluggable behind `BasePersonEnricher` / `BaseContactEnricher`.
`config/sources.yaml` registers two:

- `official_company_people` — **implemented** (the enricher above); status
  `REQUIRES_REVIEW` pending a privacy/terms review; **no key**.
- `business_contact_provider` — a **`PLANNED` / `NOT_IMPLEMENTED`** placeholder for
  a licensed B2B contact provider; it requires a commercial licence, credentials,
  and a usage policy, and its commercial use is `REQUIRES_APPROVAL`. **No paid
  provider is wired.**

Provider credentials are never exposed through the API.

### Privacy & data minimization

Business contacts are preferred over personal data. **No** personal home address,
family, private account, or private phone is collected — only publicly published,
business-relevant, source-linked, minimized data. There is **no SMTP probing** and
**no credential verification**; email is format-validated only.

### Enrichment APIs

| Method & path | Purpose |
| --- | --- |
| `GET /contacts` | List verified contacts; filters `company` / `role_category` / `verification_status` / `people_only`; paginated |
| `GET /contacts/{id}` | One contact / decision-maker record |
| `GET /companies/{id}/decision-makers` | Decision-maker rows for one company |
| `GET /companies/{id}/contacts` | Verified contacts for one company |
| `GET /leads/{id}/stakeholders` | Recommended roles + verified people/contacts + outreach readiness for a lead |
| `POST /companies/{id}/enrich` | Run the real, safe, official-source fetch for a company |

> **No live enrichment has been run against a real company** in this change. The
> enricher is unit-tested with real-shaped HTML over a mocked transport; no
> credentials are required by the default test suite.

## AI reasoning layer

A new **AI reasoning and prioritization** layer sits *over* the real,
already-verified data. It is a **reasoning layer, never a source of facts**: it
cannot invent companies, people, jobs, numbers, dates, values, technologies, or
intent. Full detail: [docs/ai-reasoning-layer.md](docs/ai-reasoning-layer.md).

> **No AI provider is configured in this environment.** Status is
> `NOT_CONFIGURED` and **no live AI request has been executed.** All AI
> intelligence shown is the **deterministic grounded baseline** produced purely
> from real DB records — nothing here means an LLM ran.

- **Deterministic baseline, always on** (`ai/deterministic.py`). With **no
  provider configured**, the layer still produces the same structured output
  purely from real DB records — executive summary, `verified_facts` (each with
  `evidence_ids`), `inferred_insights` (labelled as inference, hedged),
  `unknowns`, opportunity explanation, urgency reason, business-problem
  hypothesis, recommended action, next best action, sales angle, risk flags, and
  an AI reasoning confidence. It is stamped `model_name="deterministic-1.0"`,
  `ai_generated=false`. AI unavailable ⇒ deterministic intelligence with a clear
  indication, **never fabricated content**.
- **Fact vs inference vs unknown** (`ai/schema.py`). Every `AIClaim` carries a
  `claim_type` (`FACT` / `INFERENCE` / `UNKNOWN`), a `support_level` (`DIRECT` /
  `SUPPORTED_INFERENCE` / `UNSUPPORTED` / `CONTRADICTED`), and `evidence_ids`.
  Facts cite real evidence; inference and unknown are **never** shown as fact.
- **Grounded, minimized input context** (`ai/context.py`). The
  `LeadIntelligenceContext` / company context is assembled **only from real
  records** (scoring, canonical jobs, technologies, signals, tenders, evidence
  with `evidence_ids`, decision-makers, conflicts, provenance), **sanitized**
  (HTML/scripts stripped, length-capped) and **minimized** (no secrets, no raw
  payloads, no unnecessary personal data). A `context_hash` supports caching.
- **Provider abstraction + truthful status** (`ai/provider.py`). `BaseAIProvider`
  + `OpenAICompatibleProvider` work with any OpenAI-compatible
  `/chat/completions` endpoint, configured **only** from the environment
  (`AI_PROVIDER`, `AI_MODEL`, `AI_API_KEY`, `AI_API_BASE_URL`,
  `AI_TIMEOUT_SECONDS`, `AI_MAX_OUTPUT_TOKENS`, `AI_TEMPERATURE`, `AI_ENABLED`) —
  **no credentials in code**. Status is truthful: `NOT_CONFIGURED` / `CONFIGURED`
  / `CONNECTED` / `AUTHENTICATION_FAILED` / `RATE_LIMITED` / `ERROR` / `DISABLED`
  — `CONNECTED` **only after a real model request (probe) succeeds**. Model
  responses are strict JSON, Pydantic-validated; malformed output is rejected.
- **Prompt-injection defense** (`ai/prompts.py`). System rules are authoritative;
  source/context is passed inside a delimited **UNTRUSTED** block the model is
  told to treat as **data, not instructions**. `prompt_version` is tracked.
- **Hallucination validator** (`ai/validator.py`). AI `FACT` claims' numbers and
  named people are compared against the real context; anything ungrounded is
  marked `UNSUPPORTED_CLAIM` and the `FACT` is **downgraded to inference** so the
  UI can never show it as fact.
- **Caching, versioning & cost control** (`ai/service.py`). Orchestration is
  build context → (LLM if configured + connected + eligible, else deterministic)
  → validate → persist a **versioned** `AIIntelligenceResult`
  (`context_hash` / `output_hash` / `prompt_version` / model). The cached result
  is returned when `context_hash` + `prompt_version` are unchanged (**the
  provider is not called on every request**). The LLM runs only for **HOT / WARM**
  leads or an explicit force; others get the deterministic baseline. On provider
  failure it **falls back to deterministic** (status `UNAVAILABLE`) — no
  fabrication. Every attempt writes an `AIAnalysisAudit` (no sensitive data). AI
  reasoning confidence is a **separate axis** from `lead_score`,
  `evidence_confidence`, and `contact_confidence`.
- **Human review — no autonomous actions.** AI output is data / recommendation
  only. It **cannot** execute code, run a shell, access credentials, make HTTP
  requests, modify the schema, or send communications. High-impact actions are
  human-decided. The deterministic systems remain authoritative for source data,
  normalization, resolution, dedup, evidence verification, signal classification,
  lead score, opportunity type, and contact verification.

### AI APIs (`api/routes/ai.py`)

No secrets are exposed. `GET` returns the cached result (deterministic baseline on
the first call); `POST` forces a fresh analysis.

| Method & path | Purpose |
| --- | --- |
| `GET /ai/status` | Truthful AI provider status (currently `NOT_CONFIGURED`) |
| `GET /leads/{id}/ai-intelligence` | Cached AI intelligence for a lead (deterministic baseline first) |
| `POST /leads/{id}/ai-analyze` | Force a fresh analysis for a lead |
| `GET /companies/{id}/ai-intelligence` | Cached AI intelligence for a company |
| `POST /companies/{id}/ai-analyze` | Force a fresh analysis for a company |

**AI provider status.** No provider is configured here, so `GET /ai/status`
reports `NOT_CONFIGURED` and no live AI request has run:

| Provider | Implementation | Status | Notes |
| --- | --- | --- | --- |
| OpenAI-compatible (`ai/provider.py`) | implemented | `NOT_CONFIGURED` | Set `AI_PROVIDER` / `AI_MODEL` / `AI_API_KEY` / `AI_API_BASE_URL` (+ `AI_ENABLED`); `CONNECTED` only after a real model probe. Deterministic baseline works with none set |

**Live AI tests.** The default `pytest` suite makes **no external AI calls**.
Optional live tests are opt-in via `RUN_LIVE_AI_TESTS=true` and validate only
schema + safety, not exact wording.

## Continuous monitoring & scheduling

A **continuous monitoring & scheduling** layer keeps the real-data intelligence
current over time: it re-runs the existing collectors on configurable intervals,
**deterministically detects what actually changed** between runs (jobs, companies,
leads, opportunities, tenders, source health), and raises **in-app alerts** worth
a salesperson's attention. Full detail:
[docs/monitoring-scheduler.md](docs/monitoring-scheduler.md).

> **Monitoring detects change over REAL data; it is never a source of facts.** It
> invents nothing — every event, trend, surge, and alert derives from a real
> record already collected and verified.

> **The background scheduler runner is OFF by default and performs NO live
> collection.** It starts only when `SCHEDULER_ENABLED=true`; importing the app,
> running tests, or CI spawns no threads and makes no network calls. Even when
> enabled, a source only collects when it is actually configured.

- **Simplest appropriate technology** (`scheduler/`). A lightweight, in-process
  `asyncio` runner wraps a deterministic, clock-injectable core
  (`SchedulerService`) — **no** Celery/APScheduler/Redis/cron and no new heavy
  deps. Handlers **reuse the existing collectors, pipeline, and monitoring
  detectors** (no duplicate ingestion). Runs are idempotent (interval-bucket
  `run_key`), locked per source, retried with typed transient/permanent errors,
  and fully audited on `SchedulerRun`.
- **Deterministic detection** (`monitoring/`). Pure, unit-testable functions
  classify the eight `ChangeType`s (`REMOVED_FROM_SOURCE` is never `CLOSED`),
  hiring/technology surges (a surge is a *signal*, not a commercial conclusion),
  trends (returning `INSUFFICIENT_DATA` rather than guessing), tender deadlines,
  and source-health transitions (once per transition).
- **Change-driven AI only.** AI re-analysis runs only on a *meaningful* change,
  reuses the context-hash cache, and falls back to the deterministic grounded
  baseline — it never gates or invents a fact, and its failures never break the
  scheduler.
- **Alerting** (`notifications/`). A single service turns real Findings into
  in-app `Alert` rows after provenance gating, conservative preferences, and
  deduplication. `IN_APP` is implemented; `EMAIL`/`SLACK`/`WEBHOOK` are stubs that
  **never send until configured**.
- **/monitoring dashboard + Alert Center.** `GET /monitoring/dashboard` reports
  real pipeline counts, per-source health + latest run, jobs, recent runs, and
  alerts (plus `scheduler_enabled` and `data_mode`). The Alert Center is served by
  `GET /alerts` (+ `unread-count`, status updates) and
  `GET/PUT /notification-preferences`.

### Scheduler & alert APIs / CLI

Read endpoints are open; mutating scheduler actions are admin-guarded when
`ADMIN_API_KEY` is set (via an `X-Admin-Key` header).

| Method & path | Purpose |
| --- | --- |
| `GET /scheduler/jobs` · `/scheduler/jobs/{id}` · `/scheduler/jobs/{id}/runs` · `/scheduler/runs` | Scheduled jobs + run audit |
| `POST /scheduler/jobs/{id}/run` \| `/pause` \| `/resume` | Trigger / pause / resume a job (admin) |
| `GET /alerts` · `/alerts/unread-count` · `/alerts/{id}` · `POST /alerts/{id}/status` | Alert Center |
| `GET`/`PUT /notification-preferences` | Alert preferences |
| `GET /monitoring/dashboard` | Operational monitoring dashboard (real metrics) |

```bash
python scripts/scheduler.py list             # show jobs + status
python scripts/scheduler.py seed             # create the default job set (idempotent)
python scripts/scheduler.py run <job_name>   # run one job now (MANUAL)
python scripts/scheduler.py tick             # run all currently-due jobs once
python scripts/scheduler.py runs --limit 20  # recent run audit
```

## Business signals & tenders

Hiring is one signal; this layer adds structured **business events** and
**tenders**, a separate **commercial-intent** axis, and a per-company **timeline**,
then combines them into conservative company-level opportunity candidates. The
business-signal engine already existed; **new** here are a structured tender domain
+ pipeline, commercial-intent classification, the company timeline, and the
signals/tenders/timeline APIs. Full detail:
[docs/business-signals-and-tenders.md](docs/business-signals-and-tenders.md).

> A tender or news article never becomes a Lead on its own. A tender is classified
> first and is never treated as a sales opportunity by itself.

- **Signal types.** The deterministic detector (no LLM) classifies text into
  `BusinessSignalType` values — project awards, contracts, tenders/RFPs
  (incl. government), digital-transformation / cloud / modernization / AI /
  cybersecurity initiatives, partnerships, expansions (delivery-center /
  engineering), vendor requirements, outsourcing, and acquisitions. Both **news**
  and **tenders** become `BusinessSignal`s (the business pipeline processes
  `RecordType.NEWS_ARTICLE` **and** `RecordType.TENDER`). Tender signals flow
  through the **existing** evidence verifier — the four scores stay distinct.
- **Tender lifecycle + freshness.** `TenderRecord` stores only what the source
  states (absent values stay `NULL`, never computed). Status is `OPEN` /
  `CLOSING_SOON` / `CLOSED` / `CANCELLED` / `AWARDED` / `UNKNOWN` — from the
  source's explicit status, else from a real `closing_date` (past → `CLOSED`,
  within 7 days → `CLOSING_SOON`, future → `OPEN`); **never** inferred `OPEN` just
  because a page is reachable. Freshness uses `verification.freshness` (an expired
  or closed tender is stale). The issuing buyer (`company_id`) is kept **separate**
  from any named awarded vendor (`target_company_id`). Idempotent upsert by
  `(source_id, source_record_id)`; history is preserved (status/freshness refreshed
  on re-run, never deleted). Technologies are extracted deterministically from the
  tender content.
- **Commercial intent (separate axis).** A deterministic
  `VERY_HIGH` / `HIGH` / `MEDIUM` / `LOW` / `UNKNOWN` band from recency, source
  quality, project/tender/vendor evidence, hiring volume, technology relevance, and
  signal combination — **separate from** evidence confidence and the lead score.
  With no qualifying evidence the result is **`UNKNOWN`, not `LOW`**.
- **Company timeline.** A chronological, real-events-only timeline per company —
  business signals + tenders + observed hiring (the **canonical** job count, not a
  sum of per-source counts). It never fabricates events.
- **Cross-signal opportunity.** The core feature: strong hiring **plus** a live
  tender or fresh project/transformation signal is a stronger opportunity candidate
  than any single signal. Syndicated copies are one evidence group, not independent
  confirmations. Candidates are never auto-promoted to Leads.

### Business-signal, tender & timeline APIs

Read-only over stored real data (`api/routes/signals.py`); empty when no real data
exists.

| Method & path | Purpose |
| --- | --- |
| `GET /signals` | List business signals; filters `signal_type` / `company` / `technology` / `source`; paginated |
| `GET /signals/{id}` | One business signal |
| `GET /tenders` | List tenders; filters `status` / `technology` / `organization` / `category`; paginated |
| `GET /tenders/{id}` | One tender |
| `GET /companies/{id}/tenders` | Tenders for one company (issuer or target) |
| `GET /companies/{id}/timeline` | One company's business-event timeline |

`GET /companies/{id}/signals` (a company's business signals) already existed.

### Manual tender import CLI

Government procurement portals with no permitted public API are ingested via an
operator-driven import of REAL tenders (permitted source), never scraping:

```bash
python scripts/import_tender.py tenders.json            # ingest a JSON array of REAL tenders
python scripts/import_tender.py tenders.json --dry-run  # validate + report, persist nothing
```

Required fields: `source_id`, `external_id`/`id`, `title`. Absent fields stay
`NULL`. Provenance is `REAL`; nothing is fabricated. Imported tenders run through
the same business + tender pipelines.

### Government-source reality (verified 2026)

**No live government source is connected or executed.**

- **CPPP / GeM (`eprocure.gov.in`)** — **no documented public developer API**; the
  only programmatic access is third-party scrapers, which this project does **not**
  use. Registered `PLANNED` / **`MANUAL_SOURCE_REQUIRED`**, commercial use
  `REQUIRES_REVIEW`. Tenders enter **only** via the manual import CLI, using data an
  operator obtained through a permitted method.
- **data.gov.in (OGD Platform)** — a **legitimate open-data API**
  (`GET https://api.data.gov.in/resource/{resource_id}?api-key=&format=json`) under
  the **Government Open Data License – India (GODL)**. Needs a free API key + a
  specific dataset `resource_id`, and per-dataset field names vary (adapter
  configured per dataset). Registered **`NOT_CONFIGURED`** (env
  `DATA_GOV_IN_API_KEY` + `DATA_GOV_IN_TENDER_RESOURCE_ID`), commercial use
  `REQUIRES_REVIEW` — confirm the specific dataset's GODL terms before commercial
  reuse.

### Jooble request budget

Jooble's free REST plan is a **hard 500-request lifetime cap per key** (absolute,
**not** per period). The app persists request usage
(`source_health.requests_used` / `request_budget`); `scripts/collect.py` **caps a
run to the remaining budget**, warns at 80% consumption, and stops cleanly with
`BUDGET_EXHAUSTED` once the budget is used up. Configure the ceiling with
`JOOBLE_LIFETIME_REQUEST_BUDGET` (default `500`). Keys are per-country domain — for
India, use an `in.jooble.org` key with `JOOBLE_API_HOST=in.jooble.org`.

**Source status API** (GET endpoints make no network calls and never return
credentials):

| Method & path | Purpose |
| --- | --- |
| `GET /sources` | Truthful per-source status: implementation/config readiness, capabilities, licensing, last verified connectivity check, **and per-source ingestion metrics** (`last_ingestion_at`, `last_ingestion_records_fetched`, `last_ingestion_records_persisted`; `null` ⇒ "Not yet ingested") |
| `GET /sources/status` | Alias of `GET /sources` (same payload, incl. ingestion metrics) |
| `POST /sources/{id}/check` | On-demand real connectivity check; persists the outcome. `NOT_CONFIGURED` sources make no network call |

The Settings → Data sources UI surfaces these ingestion metrics alongside the
connectivity status.

**Live tests.** The default `pytest` suite makes **no** external network calls.
Live integration tests are opt-in via `RUN_LIVE_SOURCE_TESTS=true` plus the
relevant per-source credentials (some also gated by per-source flags such as
`ADZUNA_INTEGRATION_TEST`).
