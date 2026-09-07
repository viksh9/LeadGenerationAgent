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
| `ADZUNA_APP_ID` / `ADZUNA_APP_KEY` | Adzuna jobs API credentials (optional) | — |
| `OPENAI_API_KEY` / `OPENAI_MODEL` | Reserved for a later outreach phase | — |

See `.env.example` for the full list (Adzuna + career-page collector knobs).

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
| Adzuna Jobs API | implemented | `NOT_CONFIGURED` | Set `ADZUNA_APP_ID`/`ADZUNA_APP_KEY`; verify live before use |
| Company career pages | implemented | `REQUIRES_REVIEW` | Robots/ToS review per site before enabling |
| Company newsroom (RSS) | implemented | `REQUIRES_REVIEW` | Per-feed review before enabling |
| RSS business/tech news | implemented | `NOT_CONFIGURED` | No reviewed feeds configured |
| Government open data / procurement | planned | `PLANNED` | No collector yet |
| Project / contract registry | planned | `PLANNED` | No collector yet |
| Business database (3rd-party) | planned | `PLANNED` | Requires commercial licence |

Actual real-source ingestion (authenticating, querying, and persisting real
records) is the focus of the next phase.
