"""FastAPI entrypoint.

Exposes a health check, the lead analysis pipeline, and read access to stored
leads. The database is initialized on startup.
"""

from __future__ import annotations

import logging
from collections.abc import Generator
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, Query
from sqlalchemy.orm import Session, sessionmaker

from api.errors import register_exception_handlers
from api.schemas import (
    ErrorBody,
    HealthResponse,
    LeadAnalyzeRequest,
    LeadAnalyzeResponse,
    LeadListResponse,
    LeadResponse,
)
from config import configure_logging, get_settings
from config.exceptions import NotFoundError
from database.models import LeadStatus
from database.repository import create_session_factory, get_lead, init_db, list_leads
from processors.analysis_pipeline import AnalysisPipeline

settings = get_settings()
configure_logging()
logger = logging.getLogger(__name__)
SessionFactory: sessionmaker[Session] = create_session_factory()
pipeline = AnalysisPipeline()


@asynccontextmanager
async def lifespan(_app: FastAPI):
    logger.info("startup app=%s env=%s", settings.app_name, settings.environment)
    init_db()
    yield
    logger.info("shutdown")


app = FastAPI(
    title=settings.app_name,
    description="Discover, score, and enrich high-intent B2B leads.",
    lifespan=lifespan,
    responses={404: {"model": ErrorBody}, 500: {"model": ErrorBody}},
)
register_exception_handlers(app)


def get_session() -> Generator[Session, None, None]:
    session = SessionFactory()
    try:
        yield session
    finally:
        session.close()


@app.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    return HealthResponse(status="ok", app=settings.app_name, environment=settings.environment)


@app.post("/analyze", response_model=LeadAnalyzeResponse)
def analyze_lead(
    request: LeadAnalyzeRequest, session: Session = Depends(get_session)
) -> LeadAnalyzeResponse:
    logger.info("analyze_requested company=%s", request.company_name)
    return pipeline.analyze_and_store(session, request)


@app.get("/leads", response_model=LeadListResponse)
def get_leads(
    min_score: float = Query(default=0.0, ge=0, le=100),
    status: LeadStatus | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    session: Session = Depends(get_session),
) -> LeadListResponse:
    leads = list_leads(session, min_score=min_score, status=status, limit=limit, offset=offset)
    return LeadListResponse(
        items=[LeadResponse.model_validate(lead) for lead in leads],
        total=len(leads),
    )


@app.get("/leads/{lead_id}", response_model=LeadResponse)
def get_lead_by_id(lead_id: int, session: Session = Depends(get_session)) -> LeadResponse:
    lead = get_lead(session, lead_id)
    if lead is None:
        raise NotFoundError(f"Lead {lead_id} was not found")
    return LeadResponse.model_validate(lead)
