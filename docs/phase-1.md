# Phase 1

Phase 1 establishes a production-shaped skeleton without live web scraping.

## In scope

- Python 3.11+, FastAPI, Pydantic, SQLAlchemy, SQLite, pytest
- Package layout: `api`, `collectors`, `processors`, `intelligence`, `enrichment`, `outreach`, `database`, `config`, `tests`, `docs`, `data`
- Environment-driven settings (`config/settings.py`)
- Process logging (`config/logging.py`)
- Typed domain errors mapped to HTTP (`config/exceptions.py`, `api/errors.py`)
- Offline collector reading `data/sample_lead.json`

## Out of scope

- HTTP scraping, crawlers, or third-party search APIs
- Production auth, multi-tenant isolation, or hosted Postgres (SQLite is the default)

## How to verify

```bash
pytest
uvicorn api.main:app --reload
curl http://127.0.0.1:8000/health
```
