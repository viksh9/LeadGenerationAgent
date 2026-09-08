"""FastAPI application assembly.

Thin composition root: configure logging, CORS, exception handlers, and mount
the modular routers. All endpoint logic lives in ``api/routes`` and delegates to
the pipeline/repository layers.
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.middleware import (
    CorrelationIdMiddleware,
    RequestSizeLimitMiddleware,
    SecurityHeadersMiddleware,
)

from api.dependencies import get_session  # re-exported for tests/overrides
from api.errors import register_exception_handlers
from api.routes import (
    ai,
    alerts,
    career_sources,
    companies,
    contacts,
    crm,
    health,
    leads,
    observability,
    outreach,
    scheduler,
    signals,
    sources,
    webhooks,
)
from api.schemas import ErrorBody
from config import configure_logging, get_settings
from config.dotenv import load_dotenv
from database.repository import init_db

settings = get_settings()
configure_logging()
logger = logging.getLogger(__name__)

__all__ = ["app", "get_session"]


@asynccontextmanager
async def lifespan(_app: FastAPI):
    # Load .env into the environment so source configs (Adzuna/Jooble) that read
    # os.environ directly pick up credentials when the server actually runs.
    # Done in startup (not at import) so importing the app in tests never loads
    # real credentials or triggers network-capable code paths. Secrets never logged.
    load_dotenv()
    logger.info("startup app=%s env=%s version=%s", settings.app_name, settings.environment, settings.version)

    # Fail safely on unsafe production configuration (missing/placeholder secrets,
    # wildcard CORS, demo mode on, missing admin key). Names keys only, never values.
    from config.validation import assert_startup_config
    for issue in assert_startup_config(settings):
        logger.warning("config check [%s] %s: %s", issue.severity, issue.key, issue.message)

    init_db()

    # Continuous monitoring scheduler — started ONLY when explicitly enabled, so
    # importing the app / running tests never spawns background work or network.
    runner = None
    if settings.scheduler_active:
        from scheduler.runner import SchedulerRunner
        runner = SchedulerRunner()
        runner.start()
        logger.info("scheduler enabled: background monitoring runner started")
    else:
        logger.info("scheduler disabled (set SCHEDULER_ENABLED=true to run it)")

    yield

    if runner is not None:
        await runner.stop()
    logger.info("shutdown")


app = FastAPI(
    title=settings.app_name,
    version=settings.version,
    description="Discover, score, and enrich high-intent B2B leads.",
    lifespan=lifespan,
    responses={404: {"model": ErrorBody}, 422: {"model": ErrorBody}, 500: {"model": ErrorBody}},
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Production middleware. add_middleware stacks in reverse, so CorrelationId (added
# last) is outermost and sets the request id before anything else runs.
if settings.security_headers_enabled:
    app.add_middleware(SecurityHeadersMiddleware, hsts=settings.hsts_enabled)
app.add_middleware(RequestSizeLimitMiddleware, max_bytes=settings.max_request_bytes)
app.add_middleware(CorrelationIdMiddleware)

register_exception_handlers(app)
app.include_router(health.router)
app.include_router(leads.router)
app.include_router(companies.router)
app.include_router(sources.router)
app.include_router(career_sources.router)
app.include_router(signals.router)
app.include_router(contacts.router)
app.include_router(ai.router)
app.include_router(scheduler.router)
app.include_router(alerts.router)
app.include_router(crm.router)
app.include_router(outreach.router)
app.include_router(webhooks.router)
app.include_router(observability.router)
