# Known Limitations

Honest, complete list of what is **not** available or requires setup. Nothing here
is hidden; the platform is judged on data quality and truthfulness, not on
pretending capabilities exist.

## Sources

- **Adzuna** — implemented + configured + live-verified in development. Commercial
  use is **REQUIRES_REVIEW**: confirm Adzuna's terms for your commercial use before
  production. Free tier has limited quota.
- **Jooble** — implemented; `NOT_CONFIGURED` by default. Free key has a **lifetime
  500-request budget** enforced by the app.
- **Greenhouse / Lever (ATS)** — implemented, but require **manual board/site
  discovery** (`GREENHOUSE_BOARDS` / `LEVER_SITES`); status shows
  `DISCOVERY_REQUIRED` until configured.
- **RSS news / company career pages / newsroom** — implemented, `NOT_CONFIGURED` /
  `REQUIRES_REVIEW`; each source must be permitted (robots + terms) before use.
- **Government procurement / open-data / project registry / business databases /
  business-contact providers** — `NOT_IMPLEMENTED` (planned). Several Indian
  government procurement portals (e.g. CPPP) **do not expose a public API** and
  require manual import; a manual tender-import CLI exists.
- **Official-source people/contacts** — decision-maker enrichment only uses
  permitted official sources; where an official source does not publish a contact,
  **no contact is produced** (never guessed).

## Providers

- **AI provider** — `NOT_CONFIGURED` by default. The deterministic, evidence-
  grounded baseline always works without it; AI is a non-authoritative reasoning
  layer that never fabricates facts.
- **Email provider** — SMTP is implemented; SendGrid/Microsoft Graph/Gmail API are
  **interface stubs only** (not implemented). No email is sent unless a provider is
  configured and a human approves.
- **CRM provider** — the **internal CRM** (local DB) is the source of truth.
  External connectors (Salesforce/HubSpot/Zoho/Pipedrive) are **extension points
  only**, not implemented; naming one still uses the internal CRM.
- **Webhooks** — implemented; **fail closed** without `WEBHOOK_SECRET`.

## Platform

- **Authentication** — RBAC is a single shared `ADMIN_API_KEY` + `X-Role` header
  (ADMIN/SALES/RESEARCHER/VIEWER), not a multi-user login/IdP system. Open locally
  when no admin key is set.
- **Backups** — a documented **manual** procedure; **not automated**.
- **High availability** — **not implemented**. Single-instance deployment with
  graceful degradation.
- **Migrations** — additive-only via `init_db()` (create_all + column/index
  reconcile); there is no Alembic/down-migration framework.
- **Static SPA serving** — the API returns JSON only; the built `frontend/dist` is
  included in the image but must be served by a reverse proxy / static host / CDN.
- **Company entities from job data** — the per-record lead flow can produce leads
  without populating the `companies` table (company resolution is a separate flow).
  Leads remain fully source-traceable regardless.
- **Two normalizer/deduplicator implementations** — the wired pipeline uses
  `ingestion/job_*`; `processors/normalization` + `processors/deduplication` are
  standalone CLI variants retained for their own tests/CLI. Intentional, not dead
  code.

## Data

- **Volume is not the goal.** A run may legitimately produce many jobs and zero
  qualifying leads; the honest result is *"no production lead met the configured
  evidence and opportunity criteria."* Thresholds are never weakened to manufacture
  leads.
- Evidence records from aggregators (e.g. Adzuna) store the source **name** but not
  a per-record source **URL** (the lead carries the source URL) — reported as a
  data-quality metric, not a provenance failure.
