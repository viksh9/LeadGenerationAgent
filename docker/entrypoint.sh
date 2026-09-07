#!/usr/bin/env sh
# LeadGenerationAgent container entrypoint.
#
# Idempotent startup:
#   1. Print a NON-SECRET config summary (never echoes keys/passwords).
#   2. Ensure the DB schema exists (init_db is additive + safe to re-run). The
#      app also runs init_db() in its FastAPI lifespan, so this is belt-and-braces
#      — running it twice is harmless.
#   3. Optionally print a production-readiness report (non-fatal — never blocks
#      startup; the audit exits non-zero only on real-data/security violations).
#   4. exec uvicorn (PID 1 → clean signal handling / graceful shutdown).
#
# This script sends NO messages and configures NO providers. Email/CRM stay
# NOT_CONFIGURED unless their env vars are set, and the scheduler stays OFF unless
# SCHEDULER_ENABLED=true.
#
# Make it executable on the host if editing outside Docker:  chmod +x docker/entrypoint.sh
set -eu

API_HOST="${API_HOST:-0.0.0.0}"
API_PORT="${API_PORT:-8000}"
APP_ENV="${APP_ENV:-development}"

echo "-------------------------------------------------------------------"
echo "LeadGenerationAgent starting"
echo "  APP_ENV / ENVIRONMENT : ${APP_ENV}"
echo "  API bind              : ${API_HOST}:${API_PORT}"
echo "  DATABASE_URL          : ${DATABASE_URL:-<default sqlite:///./data/leads.db>}"
echo "  SCHEDULER_ENABLED     : ${SCHEDULER_ENABLED:-false}"
echo "  EMAIL_PROVIDER        : ${EMAIL_PROVIDER:-<unset → NOT_CONFIGURED, cannot send>}"
echo "  CRM_PROVIDER          : ${CRM_PROVIDER:-INTERNAL}"
echo "  WEBHOOK secret set    : $([ -n "${WEBHOOK_SECRET:-}" ] && echo yes || echo no)"
echo "  ADMIN_API_KEY set     : $([ -n "${ADMIN_API_KEY:-}" ] && echo yes || echo 'no (RBAC open)')"
echo "-------------------------------------------------------------------"

# 1. Ensure the schema exists (create_all + additive columns). Idempotent.
echo "[entrypoint] initialising database schema (idempotent)..."
python -c "from database.repository import init_db; init_db()"

# 2. Startup readiness report — informational only, never fatal.
echo "[entrypoint] production-readiness report (non-fatal):"
python -m app.audit production-readiness || true

# 3. Launch the API. exec so uvicorn becomes PID 1 and receives signals directly.
echo "[entrypoint] starting uvicorn api.main:app on ${API_HOST}:${API_PORT}"
exec uvicorn api.main:app --host "${API_HOST}" --port "${API_PORT}"
