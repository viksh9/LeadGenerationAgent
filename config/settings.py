"""Application settings loaded from environment variables."""

from __future__ import annotations

import sys
from functools import lru_cache
from pathlib import Path

from pydantic import AliasChoices, Field
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
    default_sample_path: Path = DATA_DIR / "sample_lead.json"
    # Whether synthetic/demo leads are shown by default. Explicitly disabled in
    # production so the dashboard never presents demo data as real. Callers can
    # still override per-request via the `provenance` query param.
    show_synthetic_leads: bool | None = Field(
        default=None,
        description="Default provenance visibility. None => derive from environment.",
        validation_alias=AliasChoices("SHOW_SYNTHETIC_LEADS", "DEMO_MODE"),
    )

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]

    @property
    def synthetic_leads_visible(self) -> bool:
        """Show synthetic leads by default only outside production."""
        if self.show_synthetic_leads is not None:
            return self.show_synthetic_leads
        return self.environment.lower() not in {"production", "prod"}


@lru_cache
def get_settings() -> Settings:
    return Settings()
