# syntax=docker/dockerfile:1
#
# LeadGenerationAgent — multi-stage image.
#
#   Stage 1 (frontend-build)  node:20-alpine  → build the React/Vite SPA to dist/
#   Stage 2 (runtime)         python:3.12-slim → FastAPI backend + built SPA
#
# No secrets are baked into the image. ALL runtime configuration comes from the
# environment (see .env.example / docs/deployment.md). The background scheduler
# is OFF unless SCHEDULER_ENABLED=true, and no email/CRM provider is configured
# unless its env vars are set — the container never sends a message on its own.

# --------------------------------------------------------------------------- #
# Stage 1 — build the frontend SPA.
# --------------------------------------------------------------------------- #
FROM node:20-alpine AS frontend-build

WORKDIR /frontend

# Install deps first (better layer caching) using the committed lockfile.
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci

# Build the production bundle → /frontend/dist. VITE_API_BASE_URL can be baked
# at build time; by default the SPA points at the same origin's API. Override
# with:  --build-arg VITE_API_BASE_URL=https://api.example.com
ARG VITE_API_BASE_URL=/
ENV VITE_API_BASE_URL=${VITE_API_BASE_URL}
COPY frontend/ ./
RUN npm run build

# --------------------------------------------------------------------------- #
# Stage 2 — Python runtime.
# --------------------------------------------------------------------------- #
FROM python:3.12-slim AS runtime

# - PYTHONDONTWRITEBYTECODE: no .pyc clutter in the layer
# - PYTHONUNBUFFERED: logs flush immediately (visible in `docker logs`)
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    APP_HOME=/app

WORKDIR ${APP_HOME}

# Install Python dependencies first for layer caching. requirements.txt pins only
# stdlib-friendly deps (fastapi, uvicorn, sqlalchemy, pydantic, httpx, pyyaml) —
# there are NO email/CRM SDKs; email uses the stdlib smtplib.
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# Copy the backend application code. (.dockerignore keeps tests, caches, the
# local .env, and the host data/ dir out of the image.)
COPY api ./api
COPY app ./app
COPY ai ./ai
COPY collectors ./collectors
COPY company ./company
COPY config ./config
COPY crm ./crm
COPY database ./database
COPY enrichment ./enrichment
COPY ingestion ./ingestion
COPY intelligence ./intelligence
COPY monitoring ./monitoring
COPY notifications ./notifications
COPY outreach ./outreach
COPY processors ./processors
COPY scheduler ./scheduler
COPY scripts ./scripts
COPY verification ./verification

# Copy the built SPA from stage 1. NOTE: api/main.py does not currently mount a
# static-file route, so the API itself serves JSON only. The bundle is included
# so an operator can serve it from a reverse proxy / static host (or add a mount
# later) — see docs/deployment.md. Copying it changes no application behaviour.
COPY --from=frontend-build /frontend/dist ./frontend/dist

# Entrypoint that idempotently initialises the DB schema, prints a (non-secret)
# startup report, then execs uvicorn.
COPY docker/entrypoint.sh /usr/local/bin/entrypoint.sh
RUN chmod +x /usr/local/bin/entrypoint.sh

# Data directory for the default SQLite DB (sqlite:///./data/leads.db). Mount a
# volume here to persist the database across container restarts.
RUN mkdir -p ${APP_HOME}/data

# Run as a non-root user. Give it ownership of the app + data dir so the DB file
# and any additive-column migrations can be written.
RUN groupadd --system app && useradd --system --gid app --home ${APP_HOME} appuser \
    && chown -R appuser:app ${APP_HOME}
USER appuser

# Sensible container defaults (all overridable via env / .env). Bind to all
# interfaces INSIDE the container; the host controls exposure via port mapping.
ENV API_HOST=0.0.0.0 \
    API_PORT=8000 \
    DATABASE_URL=sqlite:////app/data/leads.db

EXPOSE 8000

# Liveness: hit GET /health with the stdlib (no curl in the slim image).
HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD python -c "import os,urllib.request,sys; \
url='http://127.0.0.1:%s/health' % os.environ.get('API_PORT','8000'); \
sys.exit(0 if urllib.request.urlopen(url, timeout=4).status == 200 else 1)" || exit 1

ENTRYPOINT ["/usr/local/bin/entrypoint.sh"]
