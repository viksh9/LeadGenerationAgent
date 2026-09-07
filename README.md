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
| Jooble Jobs API | implemented | `NOT_CONFIGURED` | Set `JOOBLE_API_KEY` (+ `JOOBLE_API_HOST=in.jooble.org` for India); verify live before use |
| Company career pages | implemented | `REQUIRES_REVIEW` | Robots/ToS review per site before enabling |
| Company newsroom (RSS) | implemented | `REQUIRES_REVIEW` | Per-feed review before enabling |
| RSS business/tech news | implemented | `NOT_CONFIGURED` | No reviewed feeds configured |
| Government open data / procurement | planned | `PLANNED` | No collector yet |
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
