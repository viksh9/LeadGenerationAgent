# Architecture Map

A final map of the platform (Prompts 1–41). Real-data-only throughout: every
production business record is source-traceable and evidence-backed; synthetic data
exists only inside isolated tests.

## Pipeline (real data → intelligence → CRM)

```
REAL SOURCES ──► INGESTION ──► NORMALIZATION ──► DEDUPLICATION ──► COMPANY RESOLUTION
     │                                                                    │
     └────────────────────────────► EVIDENCE VERIFICATION ◄──────────────┘
                                             │
       SIGNAL DETECTION ──► OPPORTUNITY ANALYSIS ──► LEAD SCORING ──► STAKEHOLDER INTELLIGENCE
                                             │
                                     AI ANALYSIS (grounded, non-authoritative)
                                             │
        SCHEDULING ──► CHANGE DETECTION ──► ALERTS ──► CRM ──► OUTREACH (human-approved)
```

## Backend module map

| Area | Package(s) | Responsibility |
|---|---|---|
| Sources / ingestion | `collectors/`, `ingestion/` | Real-source collectors (Adzuna, Jooble, Greenhouse, Lever, RSS/career), raw persistence, run tracking, budget, SSRF-safe HTTP |
| Normalization / dedup | `processors/`, `ingestion/job_*` | Canonical jobs, content-hash + cross-source dedup |
| Company | `company/` | Entity resolution, company intelligence |
| Evidence | `verification/` | Four-score verification, freshness, conflicts |
| Intelligence | `intelligence/` | Signal detection, opportunity analysis, lead scoring, timelines |
| Enrichment | `enrichment/` | Stakeholder role recommendation, official-source contact enrichment |
| AI | `ai/` | Deterministic grounded baseline + optional provider; claims cite evidence |
| Monitoring / scheduling | `monitoring/`, `scheduler/` | Change detection, trends/surges, source health, jobs, alerts |
| Notifications | `notifications/` | In-app alerts (email/slack/webhook stubs) |
| CRM / outreach | `crm/`, `outreach/` | Lifecycle state machine, activities, sales pipeline, drafts, send, replies, webhooks, follow-ups, analytics |
| Resilience | `resilience/` | Circuit breaker |
| API | `api/` | FastAPI routes, RBAC, middleware (correlation IDs, security headers, size limits), error envelope |
| Config | `config/` | Settings, validation, logging, exceptions |
| Audits / CLI | `app/`, `scripts/` | `python -m app.audit …`, collectors/scheduler CLIs |
| Storage | `database/` | SQLAlchemy models, session/pooling, additive migrations, integrity guards |

## Data lineage (traceability contract)

```
Job:     REAL SOURCE → RawSourceRecord → NormalizedJob → JobRecord(canonical)
                     → JobSourceReference → EvidenceRecord → Lead
Company: REAL SOURCE → CompanySourceReference → Company → EvidenceRecord
Tender:  REAL SOURCE → RawSourceRecord → TenderRecord → BusinessSignal → OpportunityCandidate
Contact: REAL SOURCE → DecisionMaker (source-backed; never guessed)
AI:      REAL DB CONTEXT → AIIntelligenceResult → AIClaim(evidence_ids)
CRM:     Lead → LeadStatusHistory / CRMActivity / OutreachDraft / SalesOpportunity (audited)
```

Every production record carries `data_provenance` (or `is_synthetic` for raw
records). The `python -m app.audit provenance` command enforces this contract.

## Frontend

React + TS + Vite SPA (`frontend/`): Dashboard, Leads, Companies, Opportunities,
Signals, Tenders, Contacts, Outreach (+ real workspace), CRM, Pipeline, Analytics,
Monitoring, Settings. All values come from the real API; empty/synthetic states are
labelled honestly (no fabricated rows).

## Deployment & operations

Multi-stage Docker image (non-root, healthcheck), `docker-compose.yml`, CI
(`.github/workflows/ci.yml`). Health: `/health`, `/health/live`, `/health/ready`.
Observability: structured logs + correlation IDs, `/monitoring/metrics`. See
`docs/deployment.md`, `docs/operations-runbook.md`,
`docs/production-readiness-checklist.md`, and `docs/data-quality-and-validation.md`.
```
