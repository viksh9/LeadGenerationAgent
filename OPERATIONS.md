# Operations Guide

Day-to-day operation of LeadGenerationAgent in production. This is the top-level
operations reference; per-incident response procedures live in
[docs/operations-runbook.md](docs/operations-runbook.md).

**Real-data-only:** no operational action should ever introduce demo/dummy/
synthetic business data. When a dependency is down, the correct behaviour is
degrade gracefully and show real state / "no data" — never fabricate.

---

## Daily health checks

| Check | Command / endpoint | Healthy result |
|---|---|---|
| Process alive | `GET /health/live` | `alive` |
| Ready to serve (DB) | `GET /health/ready` | `ready`, `database: ok` |
| Operational metrics | `GET /monitoring/metrics` | counts + `circuit_breakers` all `CLOSED` |
| Source connectivity | `GET /sources` | expected sources `CONNECTED`/`CONFIGURED` |
| Scheduler runs | `GET /scheduler/runs` | recent runs `SUCCESS` (if scheduler enabled) |
| Data integrity | `python -m app.audit validate-data` | `CLEAN` |
| Provenance | `python -m app.audit provenance` | `OK` |
| Synthetic data | `python -m app.audit synthetic-data` | `DB synthetic: 0 (PASS)` |
| Production readiness | `python -m app.audit production-readiness` | `READY` |
| Go/No-Go | `python -m app.audit go-no-go` | `GO` |

Correlate any failing request by its `X-Request-ID` (returned on every response and
in every error body) against the logs.

---

## Incident response (summary)

Full procedures with "auto-recovers vs manual action" tables are in
[docs/operations-runbook.md](docs/operations-runbook.md).

- **Source API failure** — isolated; other sources + the deterministic pipeline
  continue. Transient → automatic backoff/retry; permanent (auth) → fix the
  credential env var and restart. Confirm with `POST /sources/{id}/check`.
- **Rate limiting** — source limits are honoured automatically (backoff +
  `Retry-After`); our own API 429s → raise `PUBLIC_RATE_PER_MINUTE` / front with a
  proxy limiter.
- **Database outage** — `/health/ready` returns `not_ready`; liveness stays up so
  the container is not killed on a blip; `pool_pre_ping` replaces stale
  connections. DB loss → restore from the latest verified backup (see below).
- **AI outage** — no impact: deterministic grounded baseline is used; a circuit
  breaker opens to stop hammering the provider (visible in `/monitoring/metrics`).
- **Email outage** — drafts remain; a send the provider does not confirm is
  `FAILED` (never `SENT`) and the lead is not advanced. Fix provider, re-send
  (idempotent).
- **CRM outage** — the internal CRM (local DB) stays usable; external sync
  differences become `SyncConflict` rows, never silent overwrites.
- **Scheduler failure/restart** — off unless `SCHEDULER_ENABLED=true`; runs are
  idempotent + per-source locked, so no duplicate collection/alerts/leads.
- **Enrichment failure** — no fabricated contacts; the run records the failure and
  existing verified contacts are unaffected.
- **Data-quality issue** — `python -m app.audit validate-data` reports actual
  counts; fix at source/pipeline, preserve historical evidence (never mass-delete).

---

## Backup & recovery

Backups are a **documented MANUAL procedure — NOT automated**. Full detail:
[docs/deployment.md](docs/deployment.md#database-backup--restore-sqlite).

- **Backup (SQLite):** with the app stopped, copy `data/leads.db`; or use
  `sqlite3 data/leads.db ".backup /path/backup.db"` live. Store encrypted, off-box.
- **Restore:** stop the app, replace `data/leads.db` with the backup, start; the
  additive `init_db()` reconciles any new columns/indexes on startup.
- **Validate a backup (a backup is not valid until restored):** restore into an
  isolated DB, run the app against it, run `python -m app.audit validate-data` and
  compare record counts. Never test-restore against production.
- **Recovery objectives:** RPO/RTO depend on your backup cadence — set and document
  them for your deployment; they are not fixed by the application.

For a durable multi-user deployment, point `DATABASE_URL` at Postgres and use its
native backup/PITR instead of the SQLite file.

---

## Production configuration checklist

Before serving production traffic:

1. `APP_ENV=production` (enforces `REAL_ONLY`, demo off).
2. `ADMIN_API_KEY` set (guards admin/scheduler + gates RBAC).
3. `CORS_ORIGINS` set to explicit origins (no `*`).
4. Durable `DATABASE_URL` (Postgres recommended) with backups scheduled.
5. TLS termination + `HSTS_ENABLED=true`.
6. Optional providers configured as desired (Adzuna/Jooble/AI/email/CRM); the app
   runs correctly with any of them `NOT_CONFIGURED`.
7. Gate the deploy on `python -m app.audit production-readiness` (must be `READY`).

The app **fails to start** in production if a critical config item is missing/
unsafe (placeholder secret, wildcard CORS, demo mode on, missing admin key) — it
names the offending keys only, never values.

---

## Escalation & audit trail

Every important action (status change, send, approval, config change) is recorded
in the `audit_logs` table (who / what / when / old / new / source / reason /
correlation id). Query it to reconstruct any workflow. Secrets are never logged.
