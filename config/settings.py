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

    # Continuous monitoring / scheduler (Prompt 38). The in-process background
    # runner is OFF by default so imports, tests and CI never spawn threads or
    # make network calls; enable it explicitly to run scheduled collection.
    scheduler_enabled: bool | None = Field(
        default=None,
        description="Run the in-process background scheduler. None => off (disabled).",
        validation_alias=AliasChoices("SCHEDULER_ENABLED"),
    )
    scheduler_timezone: str = Field(
        default="Asia/Kolkata", validation_alias=AliasChoices("SCHEDULER_TIMEZONE"))
    scheduler_tick_seconds: int = Field(
        default=60, validation_alias=AliasChoices("SCHEDULER_TICK_SECONDS"))
    # First-ever admin guard. When set, mutating scheduler endpoints require the
    # X-Admin-Key header. Unset (None) => allowed (local single-user default).
    admin_api_key: str | None = Field(default=None, validation_alias=AliasChoices("ADMIN_API_KEY"))

    # --- CRM / outreach lifecycle (Prompt 39) ------------------------------ #
    # Email provider. NOT_CONFIGURED unless a provider + from-address are set.
    # No message is ever sent unless a provider is configured AND a human approves.
    email_provider: str | None = Field(default=None, validation_alias=AliasChoices("EMAIL_PROVIDER"))
    email_from: str | None = Field(default=None, validation_alias=AliasChoices("EMAIL_FROM"))
    email_api_key: str | None = Field(default=None, validation_alias=AliasChoices("EMAIL_API_KEY"))
    smtp_host: str | None = Field(default=None, validation_alias=AliasChoices("SMTP_HOST"))
    smtp_port: int = Field(default=587, validation_alias=AliasChoices("SMTP_PORT"))
    smtp_username: str | None = Field(default=None, validation_alias=AliasChoices("SMTP_USERNAME"))
    smtp_password: str | None = Field(default=None, validation_alias=AliasChoices("SMTP_PASSWORD"))
    smtp_use_tls: bool = Field(default=True, validation_alias=AliasChoices("SMTP_USE_TLS"))
    # Daily send cap + per-minute rate limit (safety; never mass-sends).
    email_daily_limit: int = Field(default=100, validation_alias=AliasChoices("EMAIL_DAILY_LIMIT"))
    email_rate_per_minute: int = Field(default=10, validation_alias=AliasChoices("EMAIL_RATE_PER_MINUTE"))
    # Require a source-verified business email before sending (safety, §10).
    outreach_require_verified_email: bool = Field(
        default=True, validation_alias=AliasChoices("OUTREACH_REQUIRE_VERIFIED_EMAIL"))

    # CRM provider. INTERNAL is always available; external connectors only when
    # explicitly configured. CONNECTED only after a real provider connection.
    crm_provider: str = Field(default="INTERNAL", validation_alias=AliasChoices("CRM_PROVIDER"))
    crm_api_key: str | None = Field(default=None, validation_alias=AliasChoices("CRM_API_KEY"))
    crm_base_url: str | None = Field(default=None, validation_alias=AliasChoices("CRM_BASE_URL"))

    # Webhook signing secret (HMAC). When unset, signed webhook endpoints reject
    # all requests rather than trusting unsigned payloads.
    webhook_secret: str | None = Field(default=None, validation_alias=AliasChoices("WEBHOOK_SECRET"))
    webhook_tolerance_seconds: int = Field(
        default=300, validation_alias=AliasChoices("WEBHOOK_TOLERANCE_SECONDS"))

    # --- ContactOut POC / decision-maker enrichment (Prompt 44) ------------ #
    # Real contact enrichment only. NOT_CONFIGURED unless a token is present; no
    # call is ever made without it. The token is read from the environment only and
    # is never exposed in API responses, logs, Excel, the DB, or audit payloads.
    contactout_api_token: str | None = Field(
        default=None, validation_alias=AliasChoices("CONTACTOUT_API_TOKEN"))
    contactout_base_url: str = Field(
        default="https://api.contactout.com", validation_alias=AliasChoices("CONTACTOUT_BASE_URL"))
    contactout_enabled: bool | None = Field(
        default=None, validation_alias=AliasChoices("CONTACTOUT_ENABLED"))
    contactout_timeout_seconds: float = Field(
        default=20.0, validation_alias=AliasChoices("CONTACTOUT_TIMEOUT_SECONDS"))
    # Client-side rate limits (ContactOut documents 60/min for People Search and
    # 1000/min for other APIs). Configurable — never hard-coded through the app.
    contactout_people_search_rate_per_minute: int = Field(
        default=60, validation_alias=AliasChoices("CONTACTOUT_PEOPLE_SEARCH_RATE_PER_MINUTE"))
    contactout_other_rate_per_minute: int = Field(
        default=1000, validation_alias=AliasChoices("CONTACTOUT_OTHER_RATE_PER_MINUTE"))
    contactout_max_retries: int = Field(
        default=3, validation_alias=AliasChoices("CONTACTOUT_MAX_RETRIES"))
    contactout_backoff_cap_seconds: float = Field(
        default=30.0, validation_alias=AliasChoices("CONTACTOUT_BACKOFF_CAP_SECONDS"))
    # Credit-aware execution — conservative, configurable ceilings per opportunity.
    contactout_max_poc_searches_per_opportunity: int = Field(
        default=3, validation_alias=AliasChoices("CONTACTOUT_MAX_POC_SEARCHES_PER_OPPORTUNITY"))
    contactout_max_enrichments_per_opportunity: int = Field(
        default=2, validation_alias=AliasChoices("CONTACTOUT_MAX_ENRICHMENTS_PER_OPPORTUNITY"))
    # Reuse recent verified POC data instead of spending another credit.
    contactout_cache_ttl_hours: int = Field(
        default=168, validation_alias=AliasChoices("CONTACTOUT_CACHE_TTL_HOURS"))

    # --- Free/public intelligence enrichment (Prompt 45) ------------------- #
    # Discovers legitimately PUBLIC company + POC info from free sources (official
    # company website, GitHub public API, Wikidata) — no paid providers, no guessed
    # emails/phones, no fabricated people. Master switch + per-provider toggles.
    public_intelligence_enabled: bool | None = Field(
        default=None, validation_alias=AliasChoices("PUBLIC_INTELLIGENCE_ENABLED"))
    official_company_intelligence_enabled: bool | None = Field(
        default=None, validation_alias=AliasChoices("OFFICIAL_COMPANY_INTELLIGENCE_ENABLED"))
    github_intelligence_enabled: bool | None = Field(
        default=None, validation_alias=AliasChoices("GITHUB_INTELLIGENCE_ENABLED"))
    wikidata_intelligence_enabled: bool | None = Field(
        default=None, validation_alias=AliasChoices("WIKIDATA_INTELLIGENCE_ENABLED"))
    public_registry_intelligence_enabled: bool | None = Field(
        default=None, validation_alias=AliasChoices("PUBLIC_REGISTRY_INTELLIGENCE_ENABLED"))
    rss_intelligence_enabled: bool | None = Field(
        default=None, validation_alias=AliasChoices("RSS_INTELLIGENCE_ENABLED"))
    # Optional GitHub token — NOT required (anonymous public requests work, at a lower
    # rate limit). When present, raises the rate limit. Read from env only; never exposed.
    github_api_token: str | None = Field(default=None, validation_alias=AliasChoices("GITHUB_API_TOKEN"))
    # Descriptive User-Agent (Wikidata/GitHub etiquette) and comma-separated RSS feeds.
    public_intelligence_user_agent: str = Field(
        default="LeadGenerationAgent/1.0 (public-intelligence)",
        validation_alias=AliasChoices("PUBLIC_INTELLIGENCE_USER_AGENT"))
    rss_intelligence_feeds: str = Field(
        default="", validation_alias=AliasChoices("RSS_INTELLIGENCE_FEEDS"))
    # Per-provider client-side rate limits (requests/minute) + shared timeout.
    github_rate_per_minute: int = Field(default=30, validation_alias=AliasChoices("GITHUB_RATE_PER_MINUTE"))
    wikidata_rate_per_minute: int = Field(default=30, validation_alias=AliasChoices("WIKIDATA_RATE_PER_MINUTE"))
    public_intelligence_timeout_seconds: float = Field(
        default=20.0, validation_alias=AliasChoices("PUBLIC_INTELLIGENCE_TIMEOUT_SECONDS"))
    public_intelligence_cache_ttl_hours: int = Field(
        default=168, validation_alias=AliasChoices("PUBLIC_INTELLIGENCE_CACHE_TTL_HOURS"))

    # --- Production hardening (Prompt 40) ---------------------------------- #
    # Observability: structured JSON logs (opt-in), request/correlation IDs.
    log_format: str = Field(default="text", validation_alias=AliasChoices("LOG_FORMAT"))  # text | json
    # API safety limits.
    max_request_bytes: int = Field(default=1_000_000, validation_alias=AliasChoices("MAX_REQUEST_BYTES"))
    public_rate_per_minute: int = Field(default=120, validation_alias=AliasChoices("PUBLIC_RATE_PER_MINUTE"))
    ai_rate_per_minute: int = Field(default=20, validation_alias=AliasChoices("AI_RATE_PER_MINUTE"))
    # Security headers (HSTS only emitted when the deployment is HTTPS-terminated).
    security_headers_enabled: bool = Field(
        default=True, validation_alias=AliasChoices("SECURITY_HEADERS_ENABLED"))
    hsts_enabled: bool = Field(default=False, validation_alias=AliasChoices("HSTS_ENABLED"))
    # Database connection pool (used for non-SQLite engines; SQLite ignores these).
    db_pool_size: int = Field(default=5, validation_alias=AliasChoices("DB_POOL_SIZE"))
    db_max_overflow: int = Field(default=10, validation_alias=AliasChoices("DB_MAX_OVERFLOW"))
    db_pool_timeout: int = Field(default=30, validation_alias=AliasChoices("DB_POOL_TIMEOUT"))
    db_pool_recycle: int = Field(default=1800, validation_alias=AliasChoices("DB_POOL_RECYCLE"))

    @field_validator(
        "show_synthetic_leads", "enforce_real_data", "ai_enabled", "scheduler_enabled",
        "contactout_enabled", "public_intelligence_enabled",
        "official_company_intelligence_enabled", "github_intelligence_enabled",
        "wikidata_intelligence_enabled", "public_registry_intelligence_enabled",
        "rss_intelligence_enabled",
        mode="before",
    )
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
    def email_config_status(self) -> str:
        """Config-level email-provider status (NOT a live check). CONNECTED is only
        set after a real provider operation elsewhere."""
        provider = (self.email_provider or "").strip().upper()
        if not provider:
            return "NOT_CONFIGURED"
        if provider == "SMTP":
            ok = bool(self.smtp_host and self.email_from)
        else:  # API-key providers (SendGrid, Graph, Gmail API, ...)
            ok = bool(self.email_api_key and self.email_from)
        return "CONFIGURED" if ok else "NOT_CONFIGURED"

    @property
    def crm_config_status(self) -> str:
        """INTERNAL CRM is always CONFIGURED (local). External connectors are
        CONFIGURED only when credentials are present; CONNECTED needs a real call."""
        provider = (self.crm_provider or "INTERNAL").strip().upper()
        if provider == "INTERNAL":
            return "CONFIGURED"
        return "CONFIGURED" if self.crm_api_key else "NOT_CONFIGURED"

    @property
    def scheduler_active(self) -> bool:
        """Whether the background scheduler runner should start. Off unless
        explicitly enabled (never in tests/CI by default)."""
        return bool(self.scheduler_enabled)

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

    @property
    def contactout_config_status(self) -> str:
        """Config-level ContactOut status (NOT a live connectivity check).

        DISABLED when explicitly off; CONFIGURED when an API token is present;
        else NOT_CONFIGURED. A CONNECTED/LIVE result only comes from a real call to
        the ContactOut test endpoint — never inferred from config alone."""
        if self.contactout_enabled is False:
            return "DISABLED"
        return "CONFIGURED" if self.contactout_api_token else "NOT_CONFIGURED"

    @property
    def public_intelligence_active(self) -> bool:
        """Free/public intelligence master switch (default ON — free sources, only
        called on explicit discovery)."""
        return True if self.public_intelligence_enabled is None else bool(self.public_intelligence_enabled)

    def public_intelligence_provider_enabled(self, name: str) -> bool:
        """Whether a specific public-intelligence provider is enabled. Providers with
        no concrete data source (public_registry) or no configuration (rss without
        feeds) default OFF; the others default ON when the master switch is on."""
        if not self.public_intelligence_active:
            return False
        overrides = {
            "official_company": self.official_company_intelligence_enabled,
            "github": self.github_intelligence_enabled,
            "wikidata": self.wikidata_intelligence_enabled,
            "public_registry": self.public_registry_intelligence_enabled,
            "rss": self.rss_intelligence_enabled,
        }
        defaults = {
            "official_company": True, "github": True, "wikidata": True,
            "public_registry": False, "rss": bool(self.rss_intelligence_feeds.strip()),
        }
        val = overrides.get(name)
        return defaults.get(name, False) if val is None else bool(val)

    @property
    def public_intelligence_config_status(self) -> str:
        return "ENABLED" if self.public_intelligence_active else "DISABLED"


@lru_cache
def get_settings() -> Settings:
    return Settings()
