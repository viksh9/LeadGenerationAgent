# Launch Readiness & Real-Data Audit

This is the launch-readiness record for LeadGenerationAgent. It reports the **actual**
results of the automated audits and the truthful status of each real-data source.
Nothing here is aspirational — every claim below was produced by running the tooling
against the real configured database (`data/leads.db`, 326 real leads).

Re-run the full audit at any time:

```bash
python -m app.audit provenance
python -m app.audit synthetic-data
python -m app.audit validate-data
python -m app.audit production-readiness
python -m app.audit go-no-go
python -m app.audit source-inventory
python -m app.audit export-compliance
python -m app.audit live-sources --source adzuna   # real network request
```

## Audit results (last verified run)

| Audit | Result |
|---|---|
| `provenance` | **PASS** — 11/11 checks, 0 issues (every business record traces to a real source) |
| `synthetic-data` | **PASS** — 0 synthetic DB records; 0 runtime fabrication paths in production code |
| `validate-data` | **CLEAN** — 3487 records, 0 issues (no duplicate jobs/companies, no orphans, no missing provenance) |
| `production-readiness` | **READY** — DB reachable, additive migrations, no committed secrets, admin key gating enforced in prod |
| `go-no-go` | **GO** — all critical requirements pass |
| `export-compliance` | **PASS** — 326 rows, no demo/synthetic markers, every row source-backed |

The real-data principle is enforced structurally: an empty database is a valid state,
`init_db()` never seeds business data, and there is **no `try-real → catch → return demo`
fallback anywhere in runtime code** (verified by search across all backend + frontend
runtime packages).

## Real source test status (§35 / §43-C,D)

Only sources with configured credentials in this environment can be live-tested. Do not
read "IMPLEMENTED" as "connected" — connection is only claimed when a real request
succeeded.

| Source | Impl | Config | Live status |
|---|---|---|---|
| **Adzuna** | IMPLEMENTED | CONFIGURED | **LIVE — real request `CONNECTED OK`** (source of the 326 real leads) |
| Greenhouse / Lever | IMPLEMENTED | DISCOVERY_REQUIRED | Not tested — needs per-company ATS board tokens |
| Company career pages / newsroom | IMPLEMENTED | REQUIRES_REVIEW | Not tested — per-site terms/robots review required |
| Jooble | IMPLEMENTED | NOT_CONFIGURED | Not tested — no API key configured |
| RSS news | IMPLEMENTED | NOT_CONFIGURED | Not tested — no feeds configured |
| OpenCorporates / GitHub / Wikidata | IMPLEMENTED | env-gated | Not live-tested this run — no credentials configured |
| ContactOut / Lusha / Apollo / Hunter / Prospeo | IMPLEMENTED | NOT_CONFIGURED | Not tested — no API keys configured (per-provider `POST /integrations/{provider}/test` returns NOT_CONFIGURED, never a fake success) |
| AI provider | IMPLEMENTED | NOT_CONFIGURED | Deterministic grounded baseline only; no live model call made |

**Truthful summary:** exactly one external source (Adzuna) is live-verified. Every other
provider is honestly `NOT_CONFIGURED` / needs discovery or review, and the app degrades to
honest empty/unavailable states rather than fabricating data.

## Exports

- **Lead Data** — fixed 16-column contract, one row per company-level lead, verified
  unchanged (16 columns exact). Cell scan: 0 secrets, 0 unescaped formula-injection leads.
- **Full Intelligence** — 58 columns, 326 rows. Cell scan: 0 secrets, 0 unescaped formulas.

See [EXCEL_EXPORTS.md](EXCEL_EXPORTS.md) for the full column contract.

## Trust model (kept distinct — §10)

| Score | Meaning | Source |
|---|---|---|
| **Lead Score** | commercial relevance / priority | `intelligence/lead_scorer.py` |
| **Data Trust** | company/signal evidence quality + freshness | `official_company/trust.py` |
| **Contact Trust** | POC identity + current-employment + verification | `contact_enrichment` / public trust |
| **Signal/Source confidence** | strength of supporting evidence | verification engine |

These are independent axes and are never derived from one another.

## Production setup (§43-J)

1. `python3.11 -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt`
2. `cp .env.example .env` and set: `APP_ENV=production`, `DATABASE_URL`, `ADMIN_API_KEY`
   (required in prod), `CORS_ORIGINS`, and any real provider credentials
   (`ADZUNA_APP_ID`/`ADZUNA_APP_KEY`, etc.). `.env` is git-ignored; never commit secrets.
3. `python -m app.audit production-readiness` → must report READY.
4. Backend: `uvicorn api.main:app --host 0.0.0.0 --port 8000` (no `--reload` in prod).
5. Frontend: `cd frontend && npm ci && npm run build`; serve `frontend/dist` behind the API.
6. Health probes: liveness `GET /health/live`, readiness `GET /health/ready` (DB required;
   optional providers are informational and never flip readiness).
7. Scheduler (optional): set `SCHEDULER_ENABLED=true` to run background ingestion/refresh.
8. Backup: snapshot the SQLite DB (or your `DATABASE_URL` target) per
   [deployment.md](deployment.md) — backup is manual, not automated.

## Known limitations

- Only Adzuna is live-verified; all other providers require credentials/discovery/review
  before they can contribute real data (see the source table above).
- AI intelligence runs on the deterministic grounded baseline until an AI provider is
  configured.
- Backups are documented but not automated.

See [known-limitations.md](known-limitations.md) for the standing limitations list.
