"""Pydantic request and response models for the HTTP API."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class SignalOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    signal_type: str
    title: str
    description: str | None
    source: str | None
    source_url: str | None
    strength: float
    observed_at: datetime | None


class ContactOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    full_name: str
    title: str | None
    email: str | None
    linkedin_url: str | None
    seniority: str | None
    is_decision_maker: bool
    confidence: float


class PitchOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    subject: str
    body: str
    angle: str | None
    created_at: datetime


class CompanyOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    domain: str | None
    industry: str | None
    size: str | None
    location: str | None
    description: str | None
    signals: list[SignalOut] = Field(default_factory=list)
    contacts: list[ContactOut] = Field(default_factory=list)


class LeadOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    score: float
    intent_level: str
    opportunity_summary: str | None
    recommended_motion: str | None
    created_at: datetime
    company: CompanyOut
    pitches: list[PitchOut] = Field(default_factory=list)


class PipelineRunResponse(BaseModel):
    processed: int
    leads: list[LeadOut]


class HealthResponse(BaseModel):
    status: str
    app: str
    environment: str = "development"


class ErrorDetail(BaseModel):
    code: str
    message: str


class ErrorBody(BaseModel):
    error: ErrorDetail
