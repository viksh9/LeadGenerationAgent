# LeadGenerationAgent

AI-powered lead generation agent that discovers high-intent business opportunities, analyzes hiring and project signals, identifies decision-makers, scores prospects, and generates actionable sales intelligence.

**Phase 1** is a modular FastAPI foundation: environment-based configuration, SQLite via SQLAlchemy 2.x, a `Lead` data layer with a repository, structured logging, and typed errors. Signal detection, enrichment, outreach, AI/LLM, and any external scraping are **not** implemented yet — those arrive in later phases.

## Requirements

- Python 3.11+
- FastAPI, Pydantic, SQLAlchemy 2.x, SQLite, Uvicorn, pytest

## Layout

```
LeadGenerationAgent
├── api/                 # FastAPI app, routes (health, leads), schemas, deps
├── database/            # SQLAlchemy Lead model, enums, session, repository
├── config/              # Settings, logging, domain errors
├── intelligence/        # SignalDetector, OpportunityAnalyzer, LeadScorer,
│                        #   and the LeadAnalysisPipeline orchestrator
├── enrichment/          # POCFinder (decision-maker role recommendation)
├── outreach/            # PitchGenerator (deterministic multi-channel pitches)
├── tests/               # unit + integration
├── docs/
└── data/                # Local SQLite db (gitignored)
```

The analysis pipeline (`intelligence/lead_pipeline.py`) orchestrates the engines
end-to-end and powers `POST /leads/analyze`.

## Setup

```bash
python3.11 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

## Run the API

```bash
uvicorn api.main:app --reload
```

The `leads` table is created automatically on startup. Interactive OpenAPI docs: http://127.0.0.1:8000/docs

### Endpoints

| Method & path | Purpose |
| --- | --- |
| `GET /health` | Liveness — `{"status":"healthy","app":...,"version":...}` |
| `POST /leads` | Create a lead directly (no intelligence) → `201` |
| `POST /leads/analyze` | Run the full analysis pipeline and persist → `201` (new) / `200` (re-analyzed) |
| `GET /leads` | List with filters, search, sort, pagination |
| `GET /leads/{id}` | Fetch one lead (`404` if missing) |
| `PUT /leads/{id}` | Update editable fields (calculated fields are rejected) |
| `DELETE /leads/{id}` | Delete a lead → `204` (`404` if missing) |

`GET /leads` query params: `page` (≥1), `page_size` (1–100, default 20), `search`,
`industry`, `location`, `signal_type`, `lead_priority`, `status`, `min_score`,
`max_score`, `technology`, `sort_by` (`lead_score`|`created_at`|`updated_at`|`signal_date`|`company_name`),
`sort_order` (`asc`|`desc`). Default sort is `lead_score DESC`.

### Examples

```bash
# Health
curl localhost:8000/health

# Create a lead directly
curl -X POST localhost:8000/leads -H 'Content-Type: application/json' \
  -d '{"company_name":"Acme Corp","industry":"IT","location":"Pune"}'

# Analyze a raw signal (runs signals → opportunity → score → POC → pitch → persist)
curl -X POST localhost:8000/leads/analyze -H 'Content-Type: application/json' -d '{
  "company_name": "NorthStar Banking Technologies",
  "industry": "BFSI",
  "signal_description": "Won a major banking modernization project and is hiring 30 Java engineers, 10 AWS engineers and 5 DevOps specialists.",
  "technologies": ["Java","Spring Boot","AWS","DevOps"],
  "estimated_hiring": 45
}'

# Filtered / sorted listing
curl "localhost:8000/leads?lead_priority=HOT"
curl "localhost:8000/leads?industry=BFSI&min_score=80"
curl "localhost:8000/leads?search=banking&sort_by=lead_score&sort_order=desc&page=1&page_size=20"

# Fetch, update, delete
curl localhost:8000/leads/1
curl -X PUT localhost:8000/leads/1 -H 'Content-Type: application/json' -d '{"status":"CONTACTED"}'
curl -X DELETE localhost:8000/leads/1
```

**`POST /leads/analyze` response** (abridged): a structured `LeadAnalysisResult` with
`lead_id`, `company_name`, `signal_analysis`, `opportunity_analysis`, `scoring_result`,
`poc_recommendation`, `pitch_result`, `final_score`, `priority`, `recommended_action`, `status`.

```json
{
  "lead_id": 1,
  "company_name": "NorthStar Banking Technologies",
  "final_score": 88, "priority": "HOT", "status": "NEW",
  "signal_analysis": { "signal_types": ["HIRING","PROJECT_AWARD","DIGITAL_TRANSFORMATION"], "detected_technologies": ["Java","AWS","DevOps"] },
  "opportunity_analysis": { "opportunity_type": "LARGE_SCALE_RAMP_UP", "potential_staffing_need": "HIGH" },
  "poc_recommendation": { "primary_role": { "role": "CTO", "relevance_score": 100 } },
  "pitch_result": { "email_subject": "Scaling your Java and AWS engineering team for the new project", "message_strategy": "SCALE_UP" }
}
```

### CORS & auth

Allowed origins are configurable via `CORS_ORIGINS` (comma-separated; defaults to the
local React dev servers `http://localhost:5173,http://localhost:3000`). **Authentication/
authorization is not implemented in Phase 1 and must be added before production.**

## Frontend (React + TypeScript)

A React 18 + TypeScript + Vite SPA lives in `frontend/`. This phase ships the
**application shell only** — layout, routing, design-system primitives, the API
client, and the TanStack Query foundation. Feature pages are placeholders.

**Stack:** Vite · Tailwind CSS · React Router · TanStack Query · Axios · Lucide;
tests with Vitest + React Testing Library.

**Structure:** `src/components/{layout,ui,common}`, `src/pages`, `src/services`
(Axios client + lead API), `src/hooks` (query/mutation hooks), `src/types`
(interfaces aligned to the FastAPI schemas), `src/routes`, `src/utils`.

```bash
cd frontend
npm install
cp .env.example .env      # VITE_API_BASE_URL=http://localhost:8000
npm run dev               # http://localhost:5173
npm run build             # type-check + production build
npm run test              # Vitest
npm run lint              # ESLint (TypeScript strict)
```

**Connecting to the backend:** the client reads `VITE_API_BASE_URL` (default
`http://localhost:8000`) and calls the FastAPI endpoints. Run the API first
(`uvicorn api.main:app --reload`); its CORS already allows `http://localhost:5173`.
Only `VITE_`-prefixed vars are exposed to the browser — never put secrets there.

**Routes:** `/dashboard` (root redirects here), `/leads`, `/leads/:id`,
`/companies`, `/companies/:id`, `/opportunities`, `/contacts`, `/outreach`,
`/analytics`, `/settings`, and a Not Found catch-all.

### Dashboard

`/dashboard` is data-driven (Recharts for charts). Components live in
`src/components/dashboard/` (KPI cards, top-opportunities table, recent signals,
signal/priority distribution charts, recent activity, quick actions) and are
composed by `pages/DashboardPage.tsx`.

**Data source & calculations:** the dashboard issues a **single** `GET /leads`
query (`useDashboard` → `useLeads`, `page_size=100`, sorted by `lead_score` desc,
cached by TanStack Query) and derives every metric client-side:

- **Total Leads** uses the server-accurate `LeadListResponse.total`.
- **Hot/Warm/Qualified counts, charts, tables, activity** are computed over the
  retrieved dataset (up to 100 leads). When more leads exist than were fetched,
  the cards show a "top N of M" note.
- **Date range** (All / 7d / 30d) is applied client-side.
- **Recent Activity** is derived from lead timestamps (there is no dedicated
  activity log yet).

**Current limitations:** the backend has no aggregate/analytics endpoints and no
date filter, so cross-dataset aggregates and date filtering are dataset-limited
and computed in the browser. Signal distribution counts each lead's single
`signal_type` (list items expose one). "Analyze New Lead" is disabled (its flow
is a later phase).

## Data layer

`database/models.py` defines a single denormalized `Lead` model plus enums `SignalType`, `LeadPriority` (default `LOW`), and `LeadStatus` (default `NEW`). Sensible constraints apply only when a value is supplied: `company_name` is required, `lead_score`/`signal_confidence` fall in 0–100, and `estimated_hiring`/`project_value` are non-negative.

`database/repository.py` exposes session-based functions — no ORM usage leaks into route handlers:

```python
from database import create_session_factory, create_lead, get_lead, list_leads, update_lead, delete_lead

session = create_session_factory()()
lead = create_lead(session, company_name="NorthStar Banking Technologies", industry="BFSI")
get_lead(session, lead.id)
list_leads(session, min_score=50, limit=20)
update_lead(session, lead.id, lead_score=88.0, lead_priority="HOT")
delete_lead(session, lead.id)
```

Missing records return `None`/`False`; invalid input raises a typed `ValidationError` rather than a raw DB exception.

## Tests

```bash
pytest
```

Tests run against isolated, throwaway SQLite databases and never touch the development database.

## Configuration

Configuration is environment-based (via `.env` or process env). Defaults make local development work with no `.env`.

| Variable | Purpose | Default |
| --- | --- | --- |
| `APP_ENV` | `development`, `staging`, or `production` | `development` |
| `LOG_LEVEL` | Root log level (`INFO`, `DEBUG`, …) | `INFO` |
| `DATABASE_URL` | SQLAlchemy URL (SQLite by default) | `sqlite:///./data/leads.db` |
| `API_HOST` | Host for the API server | `127.0.0.1` |
| `API_PORT` | Port for the API server | `8000` |
| `CORS_ORIGINS` | Comma-separated allowed CORS origins | `http://localhost:5173,http://localhost:3000` |
| `OPENAI_API_KEY` | Reserved for a later outreach phase; unused in Phase 1 | — |
| `OPENAI_MODEL` | Reserved for a later outreach phase | `gpt-4o-mini` |

See `docs/architecture.md` and `docs/phase-1.md`.
