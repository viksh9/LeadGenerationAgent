"""Security + production-hardening tests (Prompt 40 §47).

Covers config/secret validation, correlation IDs, security headers, request-size
limit, RBAC, rate limiting, SSRF/URL validation, pagination caps, secret
non-leakage, and health probes. Offline; no external network.
"""

from __future__ import annotations

import pytest

from api.security import _RateLimitError, rate_limit, reset_rate_limits
from config.validation import validate_config
from config.settings import Settings


# --------------------------------------------------------------------------- #
# Config / secret / environment validation (§2, §4)
# --------------------------------------------------------------------------- #
def test_production_missing_admin_key_and_wildcard_cors_are_critical():
    prod = Settings(_env_file=None, APP_ENV="production", CORS_ORIGINS="*")
    keys = {i.key for i in validate_config(prod) if i.severity == "critical"}
    assert "ADMIN_API_KEY" in keys
    assert "CORS_ORIGINS" in keys


def test_placeholder_secret_flagged():
    prod = Settings(_env_file=None, APP_ENV="production",
                    CORS_ORIGINS="https://app.example.com", ADMIN_API_KEY="changeme")
    keys = {i.key for i in validate_config(prod) if i.severity == "critical"}
    assert "ADMIN_API_KEY" in keys   # placeholder value rejected


def test_properly_configured_production_has_no_critical_issues():
    prod = Settings(_env_file=None, APP_ENV="production",
                    CORS_ORIGINS="https://app.example.com",
                    ADMIN_API_KEY="a-real-long-random-secret-value-123456",
                    DATABASE_URL="postgresql://u:p@db/app")
    critical = [i for i in validate_config(prod) if i.severity == "critical"]
    assert critical == []


def test_error_messages_never_contain_secret_values():
    prod = Settings(_env_file=None, APP_ENV="production", ADMIN_API_KEY="changeme-supersecret-xyz")
    for issue in validate_config(prod):
        assert "supersecret" not in issue.message   # only the KEY is named, never the value


# --------------------------------------------------------------------------- #
# Middleware: correlation id, security headers, size limit (§8, §10, §26)
# --------------------------------------------------------------------------- #
def test_correlation_id_returned_and_in_error_body(client):
    r = client.get("/health")
    assert "X-Request-ID" in r.headers
    err = client.get("/scheduler/jobs/999999")
    assert "request_id" in err.json()["error"]


def test_incoming_request_id_is_propagated(client):
    r = client.get("/health", headers={"X-Request-ID": "trace-abc-123"})
    assert r.headers["X-Request-ID"] == "trace-abc-123"


def test_security_headers_present(client):
    r = client.get("/health")
    assert r.headers.get("X-Content-Type-Options") == "nosniff"
    assert r.headers.get("X-Frame-Options") == "DENY"
    assert "Content-Security-Policy" in r.headers


def test_request_size_limit_rejects_oversized_body(client):
    # Content-Length far above the default 1MB limit → 413 before body is read.
    r = client.post("/activities", content=b"{}",
                    headers={"content-type": "application/json", "content-length": str(5_000_000)})
    assert r.status_code == 413
    assert r.json()["error"]["code"] == "request_too_large"


# --------------------------------------------------------------------------- #
# RBAC (§7) — admin-only endpoints
# --------------------------------------------------------------------------- #
def test_scheduler_admin_guard_when_key_set(client, monkeypatch):
    from config import settings as sm
    monkeypatch.setattr(sm.get_settings(), "admin_api_key", "secret")
    jobs = client.get("/scheduler/jobs").json()["items"]
    jid = jobs[0]["id"]
    assert client.post(f"/scheduler/jobs/{jid}/pause").status_code == 403          # no key
    assert client.post(f"/scheduler/jobs/{jid}/pause",
                       headers={"X-Role": "SALES"}).status_code == 403             # wrong role
    ok = client.post(f"/scheduler/jobs/{jid}/pause", headers={"X-Admin-Key": "secret"})
    assert ok.status_code == 200


# --------------------------------------------------------------------------- #
# Rate limiting (§14, §43, §46)
# --------------------------------------------------------------------------- #
def test_rate_limit_dependency_raises_after_limit():
    reset_rate_limits()
    dep = rate_limit("unit-rl", 2)
    dep(); dep()                       # two allowed
    with pytest.raises(_RateLimitError) as exc:
        dep()                          # third blocked
    assert exc.value.status_code == 429


# --------------------------------------------------------------------------- #
# SSRF / URL validation (§11)
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("url", [
    "http://localhost/x", "http://127.0.0.1/x", "http://169.254.169.254/latest/meta-data",
    "http://10.0.0.5/x", "http://192.168.1.1/x", "ftp://example.com/x", "file:///etc/passwd",
])
def test_ssrf_blocks_internal_and_bad_schemes(url):
    from collectors.company.safety import SafetyError, validate_public_url
    with pytest.raises(SafetyError):
        validate_public_url(url)


def test_ssrf_allows_public_https():
    from collectors.company.safety import validate_public_url
    assert validate_public_url("https://boards.greenhouse.io/acme")


# --------------------------------------------------------------------------- #
# Pagination caps + secret non-leakage (§30, §45)
# --------------------------------------------------------------------------- #
def test_pagination_cap_rejects_huge_page_size(client):
    r = client.get("/leads", params={"page_size": 1_000_000})
    assert r.status_code == 422   # exceeds MAX_PAGE_SIZE


def test_metrics_and_provider_status_expose_no_secrets(client):
    import json
    for path in ("/monitoring/metrics", "/outreach/providers/status"):
        body = json.dumps(client.get(path).json()).lower()
        for token in ("api_key", "password", "secret", "smtp_password", "webhook_secret"):
            assert token not in body


# --------------------------------------------------------------------------- #
# Health probes (§23)
# --------------------------------------------------------------------------- #
def test_health_live_and_ready(client):
    assert client.get("/health/live").json()["status"] == "alive"
    assert client.get("/health/ready").json()["status"] == "ready"
