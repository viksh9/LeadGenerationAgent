# Deployment

How to build and run LeadGenerationAgent with Docker, the environment variables
that matter, production configuration, and the (manual) SQLite backup/restore
procedure.

> **Configuration is entirely environment-based. Credentials never live in the
> image, in Git, or in this repo.** `.env.example` holds placeholders only; the
> real `.env` is git-ignored and is read at runtime. The container sends no
> messages and configures no external provider unless you set its env vars.

## What the image contains

The [`Dockerfile`](../Dockerfile) is multi-stage:

1. **`frontend-build`** (`node:20-alpine`) runs `npm ci` + `npm run build` in
   `frontend/`, producing the Vite SPA bundle at `frontend/dist`.
2. **`runtime`** (`python:3.12-slim`) installs `requirements.txt`, copies the
   backend packages and the built SPA, creates a non-root `appuser`, exposes
   `8000`, declares a `HEALTHCHECK` against `GET /health`, and runs
   [`docker/entrypoint.sh`](../docker/entrypoint.sh).

The entrypoint idempotently initialises the DB schema
(`python -c "from database.repository import init_db; init_db()"`), prints a
non-fatal `python -m app.audit production-readiness` report, then execs
`uvicorn api.main:app`. The app *also* runs `init_db()` in its FastAPI lifespan, so
the schema is guaranteed either way.

> **The API serves JSON only.** `api/main.py` does not currently mount a
> static-file route, so it does not serve the SPA itself. The built bundle is
> included in the image at `frontend/dist` for convenience — serve it from a
> reverse proxy / static host / CDN and point its `VITE_API_BASE_URL` at the API.
> This is a documented deployment choice, not a stub in the API.

## Build & run

### Docker (single container)

```bash
cp .env.example .env            # then edit .env (placeholders → real values)
docker build -t leadgenerationagent:latest .
docker run --rm -p 8000:8000 \
    --env-file .env \
    -v leadgen-data:/app/data \
    leadgenerationagent:latest
# API at http://127.0.0.1:8000  (docs at /docs, health at /health)
```

The named volume `leadgen-data` mounted at `/app/data` persists the SQLite
database across restarts. The in-container `DATABASE_URL` defaults to
`sqlite:////app/data/leads.db`.

### Docker Compose

[`docker-compose.yml`](../docker-compose.yml) defines a single `app` service that
builds the Dockerfile, loads `.env`, maps `8000:8000`, persists `/app/data` in the
`app-data` named volume, sets `restart: unless-stopped`, and mirrors the
healthcheck:

```bash
cp .env.example .env
docker compose up --build            # build + run
docker compose logs -f app           # tail logs
docker compose down                  # stop; the named volume (and DB) are kept
docker compose down -v               # stop AND delete the data volume (destroys the DB)
```

To move off SQLite later, add a `db:` service and set `DATABASE_URL` in `.env`
(e.g. `postgresql+psycopg://user:pass@db:5432/leads`). The app reads the URL from
the environment, so no application code changes — you would only add a Postgres
driver to `requirements.txt`.

## Environment variables

Configuration is loaded by `config/settings.py` (Pydantic settings) from process
env or `.env`. Missing optional providers are a valid, healthy state.

### Required (for a production deployment)

| Variable | Purpose | Notes |
| --- | --- | --- |
| `APP_ENV` (aka `ENVIRONMENT`) | `development` / `staging` / `production` | In production this turns on real-data enforcement and turns demo/synthetic visibility off (see below). |
| `DATABASE_URL` | SQLAlchemy DB URL | Defaults to SQLite under `/app/data` in the container. |
| `ADMIN_API_KEY` | Admin key for RBAC + scheduler control | **Set this in production.** Unset ⇒ the app is fully open (single-user local default). |
| `CORS_ORIGINS` | Comma-separated allowed origins | Set to your real SPA origin(s) in production. |

### Optional — networking & app

| Variable | Purpose | Default |
| --- | --- | --- |
| `API_HOST` / `API_PORT` | Bind address inside the container | `0.0.0.0` / `8000` (image default) |
| `LOG_LEVEL` | Log verbosity | `INFO` |
| `ENFORCE_REAL_DATA` | Force write-guards on/off | Unset ⇒ on in production/staging |
| `SHOW_SYNTHETIC_LEADS` | Show synthetic leads (dev only) | Unset ⇒ off in production |

### Optional — CRM & outreach (Prompt 39)

Full detail in [docs/crm-outreach.md](crm-outreach.md). None are required; with all
unset the app drafts and approves outreach but **cannot send**.

| Variable | Purpose | Default |
| --- | --- | --- |
| `EMAIL_PROVIDER` | Email provider selector (`SMTP` implemented; others stubbed) | *(unset ⇒ NOT_CONFIGURED)* |
| `EMAIL_FROM` | From address (required for any provider) | — |
| `EMAIL_API_KEY` | Key for API-key providers (unused by SMTP, unused until implemented) | — |
| `SMTP_HOST` / `SMTP_PORT` | SMTP server | — / `587` |
| `SMTP_USERNAME` / `SMTP_PASSWORD` | SMTP login (used only if both set) | — |
| `SMTP_USE_TLS` | STARTTLS on the SMTP connection | `true` |
| `EMAIL_DAILY_LIMIT` / `EMAIL_RATE_PER_MINUTE` | Send-safety caps | `100` / `10` |
| `OUTREACH_REQUIRE_VERIFIED_EMAIL` | Require a source-verified business email to send | `true` |
| `CRM_PROVIDER` | `INTERNAL` (implemented) or an external name (not implemented) | `INTERNAL` |
| `CRM_API_KEY` / `CRM_BASE_URL` | External CRM connector config (extension point) | — |
| `WEBHOOK_SECRET` | HMAC key for signed webhooks (unset ⇒ fail closed) | — |
| `WEBHOOK_TOLERANCE_SECONDS` | Replay window | `300` |

### Optional — AI, scheduler, sources

| Variable | Purpose | Default |
| --- | --- | --- |
| `AI_PROVIDER` / `AI_MODEL` / `AI_API_KEY` / `AI_API_BASE_URL` / `AI_ENABLED` | OpenAI-compatible reasoning layer (deterministic baseline works with none set) | *(unset ⇒ NOT_CONFIGURED)* |
| `SCHEDULER_ENABLED` | Start the in-process background scheduler | `false` (**off**) |
| `SCHEDULER_TIMEZONE` / `SCHEDULER_TICK_SECONDS` | Scheduler display tz / tick cadence | `Asia/Kolkata` / `60` |
| `ADZUNA_*`, `JOOBLE_*`, `GREENHOUSE_BOARDS`, `LEVER_SITES`, `CAREER_*`, `DATA_GOV_IN_*` | Real-source collector config | see `.env.example` |

The scheduler is **off by default**; leave `SCHEDULER_ENABLED` unset/false unless
you intend the container to run background collection. See
[docs/monitoring-scheduler.md](monitoring-scheduler.md).

## Production configuration

Set `APP_ENV=production`. That single switch makes the derived settings honest:

- **`REAL_ONLY` enforced.** `real_data_only` is on in production/staging, so the
  write-guards reject synthetic/demo records and REAL leads without source-backed
  evidence (`database/integrity.py`). `data_mode` is always `REAL_ONLY` — there is
  no demo/mock runtime path.
- **Demo mode off.** `synthetic_leads_visible` is off in production, so the API
  never presents synthetic leads as real.
- **Set `ADMIN_API_KEY`.** With it set, guarded mutations require `X-Admin-Key`
  (ADMIN) or an `X-Role` header; the readiness gate also expects it in production.
  Without it the app is fully open (fine locally, **not** for production).
- **Set real `CORS_ORIGINS`.** Restrict to your SPA origin(s).
- **Keep providers explicit.** Email stays `NOT_CONFIGURED` (and thus unable to
  send) until you configure SMTP; the CRM stays `INTERNAL`; webhooks stay closed
  until `WEBHOOK_SECRET` is set.

Verify before going live:

```bash
docker compose exec app python -m app.audit production-readiness
```

It exits non-zero on any critical real-data/security violation (e.g. synthetic
records present, missing provenance, `ADMIN_API_KEY` unset in production, or a
committed-secret pattern). See
[docs/production-readiness-checklist.md](production-readiness-checklist.md).

## Health & readiness probes

| Endpoint | Meaning |
| --- | --- |
| `GET /health` | Liveness — the process is up. Used by the Docker `HEALTHCHECK`. |
| `GET /health/ready` | Readiness — verifies the **database** (required). Optional providers/scheduler are reported but never flip readiness. |

Point a load balancer / orchestrator liveness probe at `/health` and its readiness
probe at `/health/ready`.

## Database: backup & restore (SQLite)

> **Backups are a documented MANUAL procedure. Nothing in this project backs up
> the database automatically.** Schedule the commands below with your own host
> cron / operator runbook if you need recurring backups.

The database is a single SQLite file — by default `data/leads.db` (host) /
`/app/data/leads.db` (container, on the `app-data` volume).

### Back up

Prefer the online-safe `.backup` (consistent even while the app is running):

```bash
# From the container (writes into the mounted data volume):
docker compose exec app sh -c \
    'sqlite3 /app/data/leads.db ".backup /app/data/leads-$(date +%F).bak"'

# Then copy the backup out to the host:
docker compose cp app:/app/data/leads-$(date +%F).bak ./leads-$(date +%F).bak
```

Alternatively, **stop the app first** and copy the file directly (a plain copy of a
live SQLite DB can be inconsistent):

```bash
docker compose stop app
docker compose cp app:/app/data/leads.db ./leads-backup.db
docker compose start app
```

> `sqlite3` may not be present in the slim image; if `sqlite3` is unavailable, use
> the stop-and-copy method, or run `.backup` from a host with `sqlite3` against a
> copy of the volume.

### Restore

```bash
docker compose stop app
# Replace the live DB with a known-good backup, then restart.
docker compose cp ./leads-backup.db app:/app/data/leads.db
docker compose start app
```

On restart `init_db()` runs again — it is additive and non-destructive
(`create_all` + `ADD COLUMN` for any missing additive columns), so restoring an
older schema onto a newer build simply re-adds the newer columns; it never drops
data.

### Environment separation (dev / test / prod)

- Use a **separate `DATABASE_URL` (and volume) per environment** — never share one
  DB file across dev/test/prod.
- The **test suite always uses isolated throwaway SQLite databases** and never
  touches the dev/production DB; synthetic fixtures live only under
  `tests/fixtures/`.
- Set `APP_ENV` per environment so real-data enforcement and demo visibility derive
  correctly (production ⇒ enforcement on, demo off).

### Migration & recovery note

There is **no Alembic / migration framework**. The schema evolves via
`init_db()`, which is **additive only**: `create_all` creates missing tables and
`database/session.py::_reconcile_columns` runs idempotent `ALTER TABLE … ADD
COLUMN` for a curated list of additive, nullable/defaulted columns. There is no
automated column drop/rename or down-migration — destructive schema changes are
deliberately out of scope. To recover from a bad state, restore a backup as above;
`init_db()` will reconcile any additive columns on the next start.

## Security checklist (deployment)

- `.env` is git-ignored; the image `.dockerignore` excludes `.env` and local DBs —
  **no secret is ever baked into the image** or committed.
- Run behind TLS (terminate at your reverse proxy / load balancer).
- Set `ADMIN_API_KEY` and restrict `CORS_ORIGINS` in production.
- The container runs as a **non-root** user.
- The scheduler is off by default; enable it only intentionally.
- Email/CRM/webhooks stay disabled until explicitly configured — the deployment
  never sends a message on its own.
