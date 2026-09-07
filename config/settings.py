"""Application settings loaded from environment variables."""

from __future__ import annotations

import sys
from functools import lru_cache
from pathlib import Path

from pydantic import AliasChoices, Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

if sys.version_info < (3, 11):
    raise RuntimeError("LeadGenerationAgent requires Python 3.11 or newer.")

ROOT_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT_DIR / "data"


class Settings(BaseSettings):
    """Runtime configuration. Override with env vars or a local `.env` file."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "LeadGenerationAgent"
    environment: str = Field(
        default="development",
        description="development | staging | production",
        validation_alias=AliasChoices("APP_ENV", "ENVIRONMENT"),
    )
    log_level: str = "INFO"
    version: str = "0.1.0"
    database_url: str = f"sqlite:///{DATA_DIR / 'leads.db'}"
    api_host: str = "127.0.0.1"
    api_port: int = 8000
    # Comma-separated allowed CORS origins (e.g. the local React dev server).
    cors_origins: str = (
        "http://localhost:5173,http://localhost:3000,"
        "http://127.0.0.1:5173,http://127.0.0.1:3000"
    )
    openai_api_key: str | None = None
    openai_model: str = "gpt-4o-mini"
    # Whether synthetic/demo leads are shown by default. Explicitly disabled in
    # production so the dashboard never presents demo data as real. Callers can
    # still override per-request via the `provenance` query param.
    show_synthetic_leads: bool | None = Field(
        default=None,
        description="Default provenance visibility. None => derive from environment.",
        validation_alias=AliasChoices("SHOW_SYNTHETIC_LEADS", "DEMO_MODE"),
    )
    # Real-data-only enforcement. When on, write guards reject synthetic/demo
    # business records and REAL records that lack source-backed evidence
    # (see database.integrity). None => derive from environment.
    enforce_real_data: bool | None = Field(
        default=None,
        description="Reject non-real / source-less business writes. None => derive from environment.",
        validation_alias=AliasChoices("ENFORCE_REAL_DATA", "REAL_DATA_ONLY"),
    )

    # AI reasoning layer (optional). No provider is required — a deterministic,
    # evidence-grounded baseline always works. Credentials come from the env only.
    ai_provider: str | None = Field(default=None, validation_alias=AliasChoices("AI_PROVIDER"))
    ai_model: str | None = Field(default=None, validation_alias=AliasChoices("AI_MODEL"))
    ai_api_key: str | None = Field(default=None, validation_alias=AliasChoices("AI_API_KEY"))
    ai_api_base_url: str = Field(
        default="https://api.openai.com/v1", validation_alias=AliasChoices("AI_API_BASE_URL"))
    ai_timeout_seconds: float = Field(default=30.0, validation_alias=AliasChoices("AI_TIMEOUT_SECONDS"))
    ai_max_output_tokens: int = Field(default=1200, validation_alias=AliasChoices("AI_MAX_OUTPUT_TOKENS"))
    ai_temperature: float = Field(default=0.2, validation_alias=AliasChoices("AI_TEMPERATURE"))
    ai_enabled: bool | None = Field(default=None, validation_alias=AliasChoices("AI_ENABLED"))

    @field_validator("show_synthetic_leads", "enforce_real_data", "ai_enabled", mode="before")
    @classmethod
    def _empty_str_is_none(cls, value):
        """Treat an unset/empty env var (e.g. `ENFORCE_REAL_DATA=` in .env) as None
        so it derives from the environment rather than raising a parse error."""
        if isinstance(value, str) and value.strip() == "":
            return None
        return value

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]

    @property
    def synthetic_leads_visible(self) -> bool:
        """Show synthetic leads by default only outside production."""
        if self.show_synthetic_leads is not None:
            return self.show_synthetic_leads
        return self.environment.lower() not in {"production", "prod"}

    @property
    def data_mode(self) -> str:
        """The application data mode is always REAL_ONLY. There is deliberately no
        DEMO / MOCK / SYNTHETIC mode: the production app cannot display fabricated
        business data as real. (Tests use injected mocks inside the test suite only.)"""
        return "REAL_ONLY"

    @property
    def real_data_only(self) -> bool:
        """Enforce real-data-only writes. On by default in production/staging."""
        if self.enforce_real_data is not None:
            return self.enforce_real_data
        return self.environment.lower() in {"production", "prod", "staging", "stage"}

    @property
    def ai_config_status(self) -> str:
        """Config-level AI provider status (NOT a live connectivity check).

        DISABLED when explicitly off; CONFIGURED when a provider+model+key are set;
        else NOT_CONFIGURED. CONNECTED is only set by a real model request elsewhere.
        """
        if self.ai_enabled is False:
            return "DISABLED"
        if self.ai_api_key and self.ai_model and (self.ai_provider or self.ai_api_base_url):
            return "CONFIGURED"
        return "NOT_CONFIGURED"


@lru_cache
def get_settings() -> Settings:
    return Settings()
