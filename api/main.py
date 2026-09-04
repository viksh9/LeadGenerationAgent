"""FastAPI entrypoint for running the pipeline and listing scored leads."""

from __future__ import annotations

import logging
from collections.abc import Generator
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, Query
from sqlalchemy.orm import Session, sessionmaker

from api.errors import register_exception_handlers
from api.schemas import ErrorBody, HealthResponse, LeadOut, PipelineRunResponse
from config import configure_logging, get_settings
from config.exceptions import AppError, NotFoundError, PipelineError
from database.repository import LeadRepository, create_session_factory, init_db
from processors.pipeline import LeadGenerationPipeline

settings = get_settings()
configure_logging()
logger = logging.getLogger(__name__)
SessionFactory: sessionmaker[Session] = create_session_factory()


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
    responses={
        404: {"model": ErrorBody},
        500: {"model": ErrorBody},
    },
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


@app.post("/pipeline/run", response_model=PipelineRunResponse)
def run_pipeline() -> PipelineRunResponse:
    logger.info("pipeline_run_started")
    try:
        pipeline = LeadGenerationPipeline(session_factory=SessionFactory)
        leads = pipeline.run()
    except AppError:
        raise
    except Exception as exc:
        logger.exception("pipeline_run_failed")
        raise PipelineError("Pipeline failed to process sample leads.") from exc
    logger.info("pipeline_run_completed processed=%s", len(leads))
    return PipelineRunResponse(processed=len(leads), leads=[LeadOut.model_validate(lead) for lead in leads])


@app.get("/leads", response_model=list[LeadOut])
def list_leads(
    min_score: float = Query(default=0.0, ge=0, le=100),
    limit: int = Query(default=50, ge=1, le=200),
    session: Session = Depends(get_session),
) -> list[LeadOut]:
    repo = LeadRepository(session)
    return [LeadOut.model_validate(lead) for lead in repo.list_leads(min_score=min_score, limit=limit)]


@app.get("/leads/{lead_id}", response_model=LeadOut)
def get_lead(lead_id: int, session: Session = Depends(get_session)) -> LeadOut:
    lead = LeadRepository(session).get_lead(lead_id)
    if lead is None:
        raise NotFoundError(f"Lead {lead_id} was not found")
    return LeadOut.model_validate(lead)
