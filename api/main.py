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

from api.dependencies import get_session  # re-exported for tests/overrides
from api.errors import register_exception_handlers
from api.routes import health, leads
from api.schemas import ErrorBody
from config import configure_logging, get_settings
from database.repository import init_db

settings = get_settings()
configure_logging()
logger = logging.getLogger(__name__)

__all__ = ["app", "get_session"]


@asynccontextmanager
async def lifespan(_app: FastAPI):
    logger.info("startup app=%s env=%s version=%s", settings.app_name, settings.environment, settings.version)
    init_db()
    yield
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

register_exception_handlers(app)
app.include_router(health.router)
app.include_router(leads.router)
