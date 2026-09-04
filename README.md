# LeadGenerationAgent

AI-powered lead generation agent that discovers high-intent business opportunities, analyzes hiring and project signals, identifies decision-makers, scores prospects, and generates actionable sales intelligence.

Phase 1 is a modular FastAPI service with local sample data, SQLite, structured config, logging, and typed errors. External scraping is not implemented.

## Requirements

- Python 3.11+
- FastAPI, Pydantic, SQLAlchemy, SQLite, pytest

## Layout

```
LeadGenerationAgent
├── api/                 # FastAPI app, schemas, error handlers
├── collectors/          # Offline JSON collector (no scraping)
├── processors/          # Normalize + pipeline
├── intelligence/        # Signals, scoring, opportunity write-up
├── enrichment/          # Point-of-contact ranking
├── outreach/            # Pitch templates (optional OpenAI later)
├── database/            # SQLAlchemy models and repository
├── config/              # Settings, logging, domain errors
├── tests/
├── docs/
└── data/sample_lead.json
```

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

- `GET /health`
- `POST /pipeline/run` — ingest `data/sample_lead.json`, score, enrich, and draft pitches
- `GET /leads?min_score=0`
- `GET /leads/{id}`

Interactive docs: http://127.0.0.1:8000/docs

## Tests

```bash
pytest
```

## Configuration

| Variable | Purpose |
| --- | --- |
| `ENVIRONMENT` | `development`, `staging`, or `production` |
| `LOG_LEVEL` | Root log level (`INFO`, `DEBUG`, …) |
| `DATABASE_URL` | SQLAlchemy URL (SQLite by default) |
| `OPENAI_API_KEY` | Optional; unused unless outreach calls OpenAI |
| `OPENAI_MODEL` | Model for optional pitch generation |

See `docs/architecture.md` and `docs/phase-1.md`.
