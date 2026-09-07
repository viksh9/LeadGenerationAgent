# Production Readiness Checklist

A truthful, category-by-category checklist for taking LeadGenerationAgent to
production. Items are marked **[auto]** when they are verified by a command (chiefly
`python -m app.audit production-readiness` / `validate-data`) or **[manual]** when
they require an operator decision or action.

> Run the automated gate before every production deploy:
>
> ```bash
> python -m app.audit production-readiness          # exit 1 on any critical violation
> python -m app.audit production-readiness --json    # machine-readable
> python -m app.audit validate-data --fail-on-issues # data-quality gate
> ```
>
> These operate on the **real configured database** and report **actual counts**;
> they never insert or fabricate data.

## What `production-readiness` actually verifies

The command (`app/audit.py`) runs these checks. **Critical** failures make it exit
non-zero (`ready=false`); non-critical items are reported as warnings.

| Check | Category | Critical? | Verifies |
| --- | --- | --- | --- |
| `no_synthetic_records` | DATA | yes | Zero `SYNTHETIC`-provenance rows in business tables. |
| `provenance_complete` | DATA | yes | No business record is missing `data_provenance`. |
| `leads_have_evidence` | DATA | warn | REAL leads have ≥1 evidence record. |
| `demo_mode_off` | SECURITY/DATA | yes (prod) | `synthetic_leads_visible` is off in production. |
| `real_data_enforced` | DATA | yes (prod) | `real_data_only` write-guards are on in production. |
| `data_mode_real_only` | DATA | yes | `data_mode == REAL_ONLY` (no demo/mock runtime path). |
| `no_committed_secrets` | SECURITY | yes | `.env` is git-ignored and no secret-shaped literal is in `.env.example` / `config/settings.py` / `docker-compose.yml`. |
| `admin_key_set_in_prod` | SECURITY | yes (prod) | `ADMIN_API_KEY` is set when `APP_ENV=production`. |
| `email_provider_status` | SALES/DEPLOY | warn | Reports email config status (NOT_CONFIGURED is a valid state). |
| `crm_provider_status` | SALES/DEPLOY | warn | Reports CRM status (INTERNAL is CONNECTED). |
| `ai_provider_status` | AI | warn | Reports AI config status (deterministic baseline always works). |

`validate-data` additionally reports (as actual counts) records missing provenance,
synthetic records, jobs without a source reference, REAL leads without evidence,
opportunities without a supporting basis, companies without evidence confidence,
contacts without a source, duplicate canonical jobs, and orphaned CRM
activities / sales opportunities.

## DATA

- [auto] **No synthetic records** in production tables (`no_synthetic_records`).
- [auto] **Provenance complete** — every business row carries `data_provenance`
  (`provenance_complete`).
- [auto] **`REAL_ONLY` data mode** — no demo/mock/synthetic runtime path
  (`data_mode_real_only`).
- [auto] **Real-data write-guards on** in production/staging (`real_data_enforced`).
- [auto/warn] **REAL leads have evidence** (`leads_have_evidence`); investigate any
  count > 0 with `validate-data`.
- [auto] **No orphaned / unsupported records** — run `validate-data` and confirm
  `orphaned_crm_activities`, `orphaned_sales_opportunities`,
  `opportunities_without_basis`, `contacts_without_source`,
  `duplicate_canonical_jobs`, and `jobs_without_source_reference` are all `0`.
- [manual] **A backup exists** and restore has been tested — backups are a
  documented **manual** procedure (see [deployment](deployment.md#database-backup--restore-sqlite)).
- [manual] **Per-environment database** — dev/test/prod use separate
  `DATABASE_URL`s / volumes.

## SECURITY

- [auto] **No committed secrets** — `.env` git-ignored; no secret literal in tracked
  config (`no_committed_secrets`).
- [auto] **`ADMIN_API_KEY` set in production** (`admin_key_set_in_prod`).
- [manual] **RBAC understood.** RBAC is **header-based with a single shared admin
  key** (`api/security.py`): `X-Admin-Key` grants ADMIN, else the `X-Role` header
  gives SALES/RESEARCHER/VIEWER. This is **not** a multi-user auth system — there
  are no user accounts, sessions, or passwords. Treat the admin key as a shared
  secret and rotate it out-of-band.
- [manual] **CORS restricted** — `CORS_ORIGINS` set to real SPA origin(s), not the
  local dev defaults.
- [manual] **TLS terminated** at a reverse proxy / load balancer.
- [manual] **Webhooks locked down** — `WEBHOOK_SECRET` set (endpoints fail closed
  without it); replay window (`WEBHOOK_TOLERANCE_SECONDS`) reviewed.
- [auto/design] **No secret leakage** — errors use the `{"error":{"code","message"}}`
  envelope; audit/activity strings are length-capped and credential-free (by
  construction in `crm/audit.py`, `crm/webhooks.py`, provider code).
- [manual] **Non-root runtime** — confirmed (the image runs as `appuser`).

## RELIABILITY

- [design] **Idempotent startup** — `init_db()` is additive and safe to re-run
  (entrypoint + FastAPI lifespan both call it).
- [design] **Idempotent ingestion & events** — collectors skip duplicate raw
  records; CRM activities dedupe by `(source, external_id)`; webhooks dedupe by
  `(provider, provider_event_id)`; follow-ups dedupe by `dedup_key`.
- [design] **Send safety** — outreach send is guarded by approval, verified
  recipient, configured provider, daily cap, per-minute rate limit, and a per-draft
  idempotency lock; marks `SENT` only on provider confirmation
  ([crm-outreach](crm-outreach.md#send-safety-outreachsendpy)).
- [manual] **Data persistence** — the SQLite volume (`/app/data`) is on durable
  storage; `restart: unless-stopped` (or an orchestrator restart policy) is set.
- [manual] **Scheduler decision** — leave `SCHEDULER_ENABLED=false` unless the
  container is intended to run background collection.
- [manual] **Rate limiting is per-process** — note it is in-memory, not distributed;
  scaling to multiple replicas weakens the shared caps.

## OBSERVABILITY

- [auto] **Liveness** — `GET /health` returns healthy (also the Docker
  `HEALTHCHECK`).
- [auto] **Readiness** — `GET /health/ready` verifies the database; reports
  provider/scheduler status without flipping readiness.
- [manual] **Logs shipped** — `docker logs` / your log pipeline captures the
  unbuffered app logs; `LOG_LEVEL` set appropriately.
- [design] **Audit trail** — every status change / draft action / send / provider
  event writes an immutable `AuditLog` row.
- [design] **Truthful provider/source status** — `GET /outreach/providers/status`,
  `GET /sources`, `GET /ai/status`, `GET /monitoring/dashboard` report actual state,
  never "connected" without a real check.

## SALES (CRM & outreach)

- [auto/warn] **Provider status reviewed** — `email_provider_status` /
  `crm_provider_status`. Out of the box email is `NOT_CONFIGURED` (drafts can be
  approved but **not sent**); CRM is `INTERNAL`.
- [design] **Event-gated lifecycle** — `CONTACTED`/`REPLIED`/`MEETING` require a
  real event or an explicit human action, so the funnel cannot be inflated.
- [design] **Honest analytics** — conversion is `INSUFFICIENT_DATA` and pipeline
  value is `NOT_AVAILABLE` when unsupported; revenue is never inferred.
- [manual] **If enabling sending** — configure SMTP (`EMAIL_PROVIDER=SMTP`,
  `SMTP_HOST`, `EMAIL_FROM`, TLS/creds), keep `OUTREACH_REQUIRE_VERIFIED_EMAIL=true`,
  and confirm the daily/per-minute caps. There is no bulk or auto send.
- [manual] **External CRM** — Salesforce/HubSpot/Zoho connectors are **not
  implemented**; `sync_conflicts` default to `REVIEW_REQUIRED` for when one is added.

## AI

- [auto/warn] **AI status reviewed** — `ai_provider_status`. No provider is required;
  the **deterministic grounded baseline always works** and is the default.
- [design] **AI is never a source of facts** — it cannot execute code, fetch URLs,
  or send communications; its `FACT` claims are validated against real context and
  downgraded if ungrounded; failures fall back to deterministic output.
- [manual] **If enabling AI** — set `AI_PROVIDER`/`AI_MODEL`/`AI_API_KEY`
  (+`AI_ENABLED`); status becomes `CONNECTED` only after a real model probe.

## DEPLOYMENT

- [manual] **`APP_ENV=production`** set (turns on enforcement, turns off demo).
- [manual] **`.env` prepared** from `.env.example` with real values; secrets only in
  the environment.
- [auto] **Image builds** — multi-stage `docker build` succeeds (frontend + backend).
- [manual] **Volume mounted** for `/app/data`; ports mapped; healthcheck green.
- [auto] **Readiness gate green** — `python -m app.audit production-readiness` exits
  `0`.
- [manual] **Backups scheduled** by the operator (not automated by this project).
- [manual] **DB engine choice** — SQLite is fine single-instance; switch
  `DATABASE_URL` to Postgres for multi-instance (adds a driver to
  `requirements.txt`).

## Honest limitations (read before shipping)

- **Auth is a single shared admin key + role header**, not multi-user
  authentication.
- **Backups are manual** — there is no automated backup job.
- **No migration framework** — schema evolution is additive via `init_db()`; no
  down-migrations or destructive changes.
- **Rate limiting is in-process** — not shared across replicas.
- **The API does not serve the SPA** — serve `frontend/dist` separately.
- **External email/CRM connectors are not implemented** — only SMTP email and the
  internal CRM are live; the scheduler is off by default.
