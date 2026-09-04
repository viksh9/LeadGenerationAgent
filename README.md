# LeadGenerationAgent

AI-powered lead generation agent that discovers high-intent business opportunities, analyzes hiring and project signals, identifies decision-makers, scores prospects, and generates actionable sales intelligence.

**Phase 1** is a modular FastAPI foundation: environment-based configuration, SQLite via SQLAlchemy 2.x, a `Lead` data layer with a repository, structured logging, and typed errors. Signal detection, enrichment, outreach, AI/LLM, and any external scraping are **not** implemented yet — those arrive in later phases.

## Requirements

- Python 3.11+
- FastAPI, Pydantic, SQLAlchemy 2.x, SQLite, Uvicorn, pytest

## Layout

```
LeadGenerationAgent
├── api/                 # FastAPI app (/health), response schemas, error handlers
├── database/            # SQLAlchemy Lead model, enums, session, repository
├── config/              # Settings, logging, domain errors
├── collectors/          # Offline JSON collector          (scaffolding — later phase)
├── processors/          # Record normalizer               (scaffolding — later phase)
├── intelligence/        # Signals, scoring, opportunity    (scaffolding — later phase)
├── enrichment/          # Point-of-contact ranking         (scaffolding — later phase)
├── outreach/            # Pitch templates                  (scaffolding — later phase)
├── tests/
├── docs/
└── data/                # Local SQLite db (gitignored) + sample_lead.json
```

The `collectors`/`processors`/`intelligence`/`enrichment`/`outreach` packages contain self-contained building blocks for future phases; they are unit-tested but not wired into the API in Phase 1.

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

- `GET /health` — returns `{"status": "ok", "app": ..., "environment": ...}`

The `leads` table is created automatically on startup. Interactive docs: http://127.0.0.1:8000/docs

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
| `OPENAI_API_KEY` | Reserved for a later outreach phase; unused in Phase 1 | — |
| `OPENAI_MODEL` | Reserved for a later outreach phase | `gpt-4o-mini` |

See `docs/architecture.md` and `docs/phase-1.md`.
