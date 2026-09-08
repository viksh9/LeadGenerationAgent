"""Startup configuration + secret validation (Prompt 40 §2, §4).

Production must fail SAFELY when critical configuration is missing or unsafe:
missing/placeholder secrets, wildcard CORS, demo mode on, or a missing admin key.
Non-production environments only warn. Error messages name the offending
configuration KEY only — actual secret values are NEVER printed or logged.
"""

from __future__ import annotations

from dataclasses import dataclass

from config.settings import Settings, get_settings

_KNOWN_ENVIRONMENTS = {"test", "development", "dev", "local", "staging", "stage", "production", "prod"}
_PROD = {"production", "prod"}

# Substrings that mark a value as a placeholder / non-real secret. Compared
# case-insensitively; we check the value's shape, never log the value itself.
_PLACEHOLDER_MARKERS = (
    "changeme", "change-me", "change_me", "placeholder", "your-", "your_", "yourkey",
    "example", "dummy", "replace-me", "replaceme", "todo", "xxxx", "<", "sk-xxx",
)
_PLACEHOLDER_EXACT = {"secret", "password", "admin", "test", "key", "apikey", "api_key",
                      "changeme", "none", "default", "secret-key", "test-secret"}

# Secret-bearing settings attributes to validate when set.
_SECRET_KEYS = (
    "admin_api_key", "ai_api_key", "email_api_key", "smtp_password", "crm_api_key", "webhook_secret",
)


@dataclass(frozen=True)
class ConfigIssue:
    key: str
    severity: str        # "critical" | "warning"
    message: str         # names the key only; never contains a secret value


def _looks_like_placeholder(value: str) -> bool:
    v = value.strip().lower()
    if not v:
        return True
    if v in _PLACEHOLDER_EXACT:
        return True
    return any(marker in v for marker in _PLACEHOLDER_MARKERS)


def validate_config(settings: Settings | None = None) -> list[ConfigIssue]:
    """Return all configuration issues. Critical issues abort production startup."""
    settings = settings or get_settings()
    env = (settings.environment or "").strip().lower()
    is_prod = env in _PROD
    issues: list[ConfigIssue] = []

    def crit(key, msg):
        issues.append(ConfigIssue(key, "critical" if is_prod else "warning", msg))

    def warn(key, msg):
        issues.append(ConfigIssue(key, "warning", msg))

    # Recognised environment.
    if env not in _KNOWN_ENVIRONMENTS:
        warn("APP_ENV", f"unrecognised environment '{settings.environment}'")

    # Any SET secret must not be a placeholder/default (all environments).
    for key in _SECRET_KEYS:
        value = getattr(settings, key, None)
        if value and _looks_like_placeholder(str(value)):
            issues.append(ConfigIssue(
                key.upper(), "critical" if is_prod else "warning",
                f"{key.upper()} appears to be a placeholder/default value; set a real secret",
            ))

    if is_prod:
        # Real-data-only must be enforced; demo/synthetic visibility must be off.
        if not settings.real_data_only:
            crit("ENFORCE_REAL_DATA", "production must enforce real-data-only writes")
        if settings.synthetic_leads_visible:
            crit("SHOW_SYNTHETIC_LEADS", "demo/synthetic visibility must be OFF in production")
        if settings.data_mode != "REAL_ONLY":
            crit("DATA_MODE", "data mode must be REAL_ONLY in production")

        # CORS must be explicit (no wildcard).
        origins = settings.cors_origin_list
        if not origins or "*" in origins:
            crit("CORS_ORIGINS", "production CORS must list explicit origins (no '*')")

        # The admin/RBAC key must be set so mutating/admin endpoints are guarded.
        if not settings.admin_api_key:
            crit("ADMIN_API_KEY", "production requires an ADMIN_API_KEY to guard admin/scheduler actions")

        # Warn (not fatal) if production still uses the bundled dev SQLite file.
        if settings.database_url.endswith("data/leads.db") or ":memory:" in settings.database_url:
            warn("DATABASE_URL", "production is using the bundled dev SQLite database; configure a durable DB")

    return issues


def assert_startup_config(settings: Settings | None = None) -> list[ConfigIssue]:
    """Validate config at startup. In production, raise RuntimeError listing the
    offending KEYS (never values) if any critical issue exists. Returns the issue
    list (for logging) in all cases. Safe to call from the app lifespan."""
    settings = settings or get_settings()
    issues = validate_config(settings)
    critical = [i for i in issues if i.severity == "critical"]
    if critical:
        keys = ", ".join(sorted({i.key for i in critical}))
        raise RuntimeError(
            f"Unsafe production configuration — fix these keys before startup: {keys}. "
            f"(No secret values are shown; see docs/deployment.md.)"
        )
    return issues
