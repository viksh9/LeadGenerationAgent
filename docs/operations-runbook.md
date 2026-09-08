# Operations Runbook

Response procedures for common production incidents. This platform is
**real-data-only**: no incident response should ever introduce demo, dummy, or
synthetic business data. When a dependency is down, the correct behaviour is
**degrade gracefully and show real state / "no data"** — never fabricate.

> Legend for status honesty (per Prompt 40 §62): **IMPLEMENTED** (code exists),
> **CONFIGURED** (env set), **LIVE-VERIFIED** (observed working against the real
> dependency). Do not claim a higher level than was actually verified.

---

## Quick reference

| Concern | Where to look |
|---|---|
| Is the process alive? | `GET /health/live` |
| Can it serve traffic (DB ok)? | `GET /health/ready` |
| Operational metrics | `GET /monitoring/metrics` |
| Source connectivity | `GET /sources` (+ `POST /sources/{id}/check`) |
| Scheduler jobs/runs | `GET /scheduler/jobs`, `GET /scheduler/runs` |
| Email/CRM provider status | `GET /outreach/providers/status` |
| Data quality | `python -m app.audit validate-data` |
| Production readiness | `python -m app.audit production-readiness` |
| Correlation of a failing request | `X-Request-ID` response header / `request_id` in error body / logs |

---

## 1. Source API failure (Adzuna / Jooble / ATS / news)

**Symptom:** a source shows `ERROR`/`TEMPORARILY_UNAVAILABLE` in `GET /sources`;
collection runs record failures.

**Impact:** isolated — one source failing does NOT stop others, and does not stop
the deterministic pipeline (§33).

**Response:**
1. `POST /sources/{id}/check` to record current connectivity truthfully.
2. Inspect `GET /scheduler/runs` for the failing job's error (sanitized).
3. Transient (5xx/timeout/rate-limit) → the scheduler retries with backoff; no
   action needed. Confirm recovery via a later run / `SOURCE_RECOVERED` event.
4. Permanent (auth/4xx) → fix the credential env var and restart; the source
   stays `AUTHENTICATION_FAILED` until a real successful check.

## 2. Rate limiting (a source or our own API)

- **Source rate-limited:** honoured automatically (backoff + `Retry-After`); the
  budget guard (e.g. Jooble lifetime cap) prevents overuse. No action unless the
  cap is exhausted — then wait for reset or raise the documented budget.
- **Our API returning 429:** in-process per-minute limits on send/webhooks/AI.
  Legitimate load → raise `PUBLIC_RATE_PER_MINUTE` / `AI_RATE_PER_MINUTE`. Abuse
  → front the API with a reverse-proxy/WAF rate limiter.

## 3. Database outage

**Symptom:** `GET /health/ready` returns `not_ready` with `database: error`.

**Response:**
1. Liveness (`/health/live`) still returns 200 — do NOT kill the container on a
   transient DB blip; readiness gates traffic instead.
2. `pool_pre_ping` replaces stale connections automatically after the DB returns.
3. If the DB is lost, follow **Disaster recovery** in `docs/deployment.md`
   (restore from the latest verified backup). Backups are **manual** — do not
   assume an automated backup exists unless one was configured.

## 4. AI provider outage

**Impact:** none to core intelligence. AI is change-driven and non-authoritative;
on failure the system uses the **deterministic grounded baseline** and marks the
result `UNAVAILABLE` — it never fabricates AI output (§32). A circuit breaker
(`ai_provider`) opens after repeated failures and stops calling the provider until
it recovers; state is visible in `GET /monitoring/metrics` → `circuit_breakers`.

**Response:** usually none. Verify recovery via the breaker returning to `CLOSED`.

## 5. Email provider outage

**Impact:** drafts remain available; nothing is auto-sent. A send that the
provider does not confirm is marked `FAILED` (never `SENT`), and the lead is NOT
advanced to CONTACTED (§11).

**Response:** check `GET /outreach/providers/status`. Fix SMTP/provider env, then
re-send the specific approved draft (`POST /outreach/{id}/send`) — idempotency
prevents duplicate sends.

## 6. CRM provider outage

**Impact:** the internal CRM (local DB) is the source of truth and stays fully
usable. External sync (if ever configured) is additive; unresolved differences
become `SyncConflict` rows rather than silent overwrites (§64).

## 7. Scheduler failure / restart

**Impact:** the scheduler is OFF unless `SCHEDULER_ENABLED=true`. Runs are
idempotent (per-interval `run_key`) and locked per source, so a restart cannot
double-collect or double-process.

**Response:** on restart the runner re-seeds jobs idempotently and resumes on the
next tick. Inspect `GET /scheduler/runs`; manually trigger a job with
`POST /scheduler/jobs/{id}/run` (admin) if a cycle was missed.

## 8. Authentication / authorization failure

- 403 on admin/scheduler endpoints with `ADMIN_API_KEY` set → supply a valid
  `X-Admin-Key`. On other mutations → supply an `X-Role` of SALES/ADMIN.
- Lost admin key → rotate `ADMIN_API_KEY` and restart. Never log or commit it.

## 9. Corrupted or duplicate ingestion

**Response:**
1. `python -m app.audit validate-data` — reports duplicate canonical jobs,
   orphans, missing provenance/evidence with **actual counts**.
2. Duplicates: ingestion is content-hash + external-id deduplicated; a spike
   usually means a source changed its ID scheme — inspect and adjust the
   collector, do not mass-delete real evidence.
3. Synthetic contamination (should be 0): `python scripts/db_audit.py
   --purge-synthetic` removes ONLY synthetic rows, and only in safe environments.

## 10. Data-quality issue

Run `validate-data`; triage by category (missing evidence/source, invalid status,
orphan). Fix at the source/pipeline; preserve historical evidence — do not delete
business intelligence merely because it is old (§43).

---

## Startup safety

In `production`, the app **fails to start** (fail-safe) when critical config is
missing/unsafe: placeholder/absent secrets, wildcard CORS, demo mode on, or a
missing `ADMIN_API_KEY`. The error names only the offending **keys** — never
values. Fix the keys (see `.env.example` / `docs/deployment.md`) and restart.

## Which components auto-recover vs need manual action

| Failure | Auto-recovers? | Manual action |
|---|---|---|
| Source transient error / rate limit | Yes (retry/backoff) | None |
| Source auth failure | No | Fix credential, restart |
| DB transient blip | Yes (pool pre-ping) | None |
| DB loss | No | Restore from backup |
| AI provider down | Yes (deterministic fallback + breaker) | None |
| Email provider down | Partial (drafts safe) | Fix provider, re-send |
| Scheduler restart | Yes (idempotent) | Optional manual run |

High availability (multi-instance, failover) is **NOT implemented** — do not
claim it. This is a single-instance deployment with graceful degradation.
