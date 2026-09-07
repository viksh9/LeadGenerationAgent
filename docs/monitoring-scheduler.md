# Continuous Monitoring & Scheduling Layer

This layer keeps the platform's real-data intelligence **current** over time. It
re-runs the existing collectors on configurable intervals, deterministically
**detects what actually changed** between runs, and raises **in-app alerts** for
the changes worth a salesperson's attention — jobs, companies, leads,
opportunities, tenders, and source health.

> **Monitoring detects change over REAL data; it is never a source of facts.**

It cannot invent companies, jobs, tenders, signals, people, numbers, or dates.
Every event, trend, surge, and alert it emits is derived from a real record that
was already collected, normalized, resolved, verified, and scored by the
deterministic pipeline. AI is **never** called to produce a fact here, and the
background runner is **OFF by default**.

> **No background collection runs in this environment.** The in-process scheduler
> runner is disabled unless `SCHEDULER_ENABLED=true` is set. Merely reading this
> document, importing the app, or running the test suite starts **no** threads and
> makes **no** network calls. With the runner off, the monitoring/scheduler code
> is still exercised on demand (API, CLI) but only over data already in the DB.

## Design philosophy

- **Real-data-only.** Detection reads REAL records exclusively
  (`data_provenance == REAL`). An empty database is a valid state — the monitoring
  dashboard and Alert Center simply show nothing, never fabricated activity.
- **Deterministic detection.** Every change/trend/surge/tender/source-health
  verdict is computed by pure, unit-testable functions with an injected `now` —
  no wall-clock, no randomness, no LLM. The same inputs always yield the same
  events.
- **AI is change-driven and never authoritative.** AI re-analysis runs only when a
  *meaningful* change is detected, reuses the existing context-hash cache, and
  falls back to the deterministic grounded baseline when no provider is
  configured. It never gates, corrects, or invents a fact.
- **Recalculation is not a change.** An event is emitted only when the resulting
  state *materially differs* from before — recomputing a lead, opportunity, or
  signal that lands on the same values produces no event and no alert.
- **Off by default.** The scheduler starts no work unless explicitly enabled, and
  every source still collects only when it is actually configured.

## Where it sits

The deterministic pipeline stays authoritative for source data, normalization,
entity resolution, deduplication, evidence verification, signal classification,
lead score, opportunity type, and contact verification. This layer is an
*orchestrator + observer* over that pipeline — it reuses the existing collectors
and services and never reimplements ingestion:

```
SCHEDULER (scheduler/)                       ← when/what to run (off by default)
  → HANDLERS (scheduler/handlers.py)         reuse collectors + pipeline + monitoring
      → COLLECT (existing collectors/)       real sources, only when configured
      → PIPELINE (existing ingestion/)       raw → normalize → dedup → resolve → verify → score
  → DETECT (monitoring/)                     deterministic change/trend/tender/source-health
      → FINDINGS (monitoring/findings.py)    proposed alert-worthy facts (REAL)
  → NOTIFY (notifications/)                   Findings → Alert rows (dedup + prefs + provenance)
  → REPROCESS (scheduler/reprocess.py)       event-driven re-verify/re-score + change-driven AI
  → AUDIT (SchedulerRun)                      actual counters per execution
```

Detection and alerting are deliberately separate: detectors emit **Findings**
from real data and never decide notification policy; the single
`NotificationService` is the only writer of `Alert` rows and never re-derives
facts.

## Scheduler technology choice — the simplest appropriate technology

The scheduler is a **lightweight, in-process `asyncio` runner** wrapped around a
**deterministic, clock-injectable core** (`SchedulerService`). There is
deliberately **no** Celery, APScheduler, Redis, cron, or external broker.

Why this is the right choice for this app:

- **No new heavy dependencies / no new infrastructure.** The app is a single
  FastAPI process over SQLite. A broker or worker fleet would add operational
  weight far beyond what interval-based refresh of a handful of sources needs.
- **Deterministic and testable.** The core (`due_jobs`, `run_job`, `tick`) takes
  `now` as an argument and holds no ambient time or network. It is unit-tested
  without spawning threads, sleeping, or hitting a network — the exact property a
  cron/broker-based design makes hard.
- **Reuses existing collectors and pipeline.** Handlers call the *same*
  `JobCollectionService`, `run_company_pipeline`, monitoring detectors, and
  notification service that the manual CLIs use — there is no second ingestion
  path to keep in sync.
- **Safe by construction.** The background loop lives behind
  `settings.scheduler_active`; importing the app, running tests, or CI never
  starts it (`scheduler/runner.py`). State (jobs, runs, locks) lives in the DB and
  process memory — nothing to provision.

The `SchedulerRunner` is a single `asyncio` task that periodically calls
`SchedulerService.tick()` on a worker thread (`asyncio.to_thread`), opening its
own DB session per tick and committing per run. A crashing tick is logged and the
loop continues — no silent death.

## Data models & enums

New tables (all created by `init_db()` schema-only; no data is seeded):

| Model | Table | Purpose |
| --- | --- | --- |
| `ScheduledJob` | `scheduled_jobs` | Config + live state of one recurring job (interval, source, retry policy, `next_run_at`, `current_status`). Unique by `job_name`. |
| `SchedulerRun` | `scheduler_runs` | Per-execution audit: trigger, status, duration, real counters, error. Unique by `run_key` (idempotency). |
| `JobChangeEvent` | `job_change_events` | A detected canonical-job change (type + field diff + significance). Unique by `dedup_key`. |
| `CompanyChangeEvent` | `company_change_events` | Company-level change (hiring surge/trend, new tech demand, new decision-maker, project signal). |
| `LeadChangeEvent` | `lead_change_events` | Lead-level change (score/priority movement, evidence, conflict, contact verified, stale, outreach-ready). |
| `OpportunityChangeEvent` | `opportunity_change_events` | Material opportunity change (created, strengthened/weakened, type change, resolved). |
| `SourceHealthEvent` | `source_health_events` | Operational source connectivity transition (failed/recovered/rate-limited/auth-failed). Never a business lead. |
| `Alert` | `alerts` | In-app notification derived from a REAL finding. Unique by `deduplication_key`. |
| `NotificationPreference` | `notification_preferences` | Conservative per-scope alert preferences (single-user → one `DEFAULT` row). |

Every change/alert model carries a `dedup_key`/`deduplication_key` unique
constraint, a `detected_at`/`triggered_at` timestamp, and (for business rows)
`data_provenance = REAL`. Change/alert rows are **append-only** (see
[Data retention](#data-retention)).

New enums:

| Enum | Values |
| --- | --- |
| `JobType` | `SOURCE_COLLECTION`, `EVIDENCE_REVERIFICATION`, `COMPANY_ENRICHMENT`, `SIGNAL_RECOMPUTATION`, `OPPORTUNITY_RECOMPUTATION`, `AI_REANALYSIS`, `NOTIFICATION_DISPATCH`, `SOURCE_HEALTH_CHECK`, `TENDER_DEADLINE_SCAN` |
| `ScheduledJobStatus` | `DISABLED`, `SCHEDULED`, `RUNNING`, `SUCCESS`, `FAILED`, `PAUSED` |
| `SchedulerRunStatus` | `RUNNING`, `SUCCESS`, `FAILED`, `SKIPPED` (idempotency/lock — not an error), `PARTIAL` (recoverable errors) |
| `ChangeType` | `NEW`, `UPDATED`, `UNCHANGED`, `CLOSED`, `REMOVED_FROM_SOURCE`, `REOPENED`, `STALE`, `CONTRADICTED` |
| `ChangeSignificance` | `CRITICAL`, `HIGH`, `MEDIUM`, `LOW` |
| `TrendStatus` | `RAPIDLY_INCREASING`, `INCREASING`, `STABLE`, `DECREASING`, `RAPIDLY_DECREASING`, `INSUFFICIENT_DATA` |
| `AlertType` | `NEW_HIGH_INTENT_LEAD`, `LEAD_SCORE_INCREASED`, `LEAD_PRIORITY_INCREASED`, `HIRING_SURGE`, `NEW_PROJECT`, `NEW_TENDER`, `TENDER_CLOSING_SOON`, `NEW_TECHNOLOGY_SIGNAL`, `NEW_DECISION_MAKER`, `CONTACT_VERIFIED`, `EVIDENCE_CONFLICT`, `EVIDENCE_STALE`, `SOURCE_FAILURE`, `SOURCE_RECOVERED` |
| `AlertSeverity` | `CRITICAL`, `HIGH`, `MEDIUM`, `LOW` |
| `AlertStatus` | `NEW`, `ACKNOWLEDGED`, `DISMISSED`, `RESOLVED` |
| `SourceHealthEventType` | `SOURCE_CONNECTED`, `SOURCE_FAILED`, `SOURCE_RATE_LIMITED`, `SOURCE_AUTH_FAILED`, `SOURCE_RECOVERED`, `SOURCE_SCHEMA_CHANGED` |

## Configurable policy (`monitoring/config.py`)

Cadence, thresholds, and significance rules live in `MonitoringConfig` — **not**
in business logic — so tuning never touches detection or scheduler code. Values
are conservative defaults; any engine accepts a custom config for testing/tuning.

- `DEFAULT_SOURCE_INTERVALS` — per-source-category collection cadence
  (jobs `6h`, tenders `6h`, news `12h`, business `12h`, default `12h`). These are
  **seeds** for `ScheduledJob` rows; once a job exists its own `interval_seconds`
  always wins.
- `DEFAULT_JOB_INTERVALS` — cadence for maintenance job types (e.g. evidence
  re-verification daily, notification dispatch every 15m, AI re-analysis daily and
  change-driven).
- `SurgeConfig` (hiring / technology), `TrendConfig`, `TenderMonitorConfig`,
  `SourceHealthConfig`, `LeadChangeConfig`, `AlertConfig` — the tunable bands
  described in the sections below.

## Change-detection semantics (`monitoring/change_detection.py`)

`classify_job_change` is a **pure** function comparing a previous and current
`JobSnapshot` (built only from REAL `JobRecord` columns) and returning a verdict
(change type + significance + field-level diffs). `detect_job_changes` is the
driver that builds snapshots from real records and persists idempotent
`JobChangeEvent` rows.

The eight `ChangeType` values:

| Change type | When | Significance |
| --- | --- | --- |
| `NEW` | A canonical job observed for the first time. | `MEDIUM` |
| `UPDATED` | Content hash changed; emits per-field diffs (technologies/location `MEDIUM`; title/salary/employment/date `LOW`). Overall significance = max of the changed fields. | field-driven |
| `UNCHANGED` | No content change and not stale. | `LOW` (no event persisted) |
| `CLOSED` | Explicit closed/expired **source status** only. | `CRITICAL` |
| `REMOVED_FROM_SOURCE` | The job disappeared from the source listing. | `MEDIUM` |
| `REOPENED` | A previously closed job is active again. | `HIGH` |
| `STALE` | No content change but freshness marks it stale. | `MEDIUM` |
| `CONTRADICTED` | The evidence layer flagged contradicting evidence. | `CRITICAL` |

> **`REMOVED_FROM_SOURCE` is NOT `CLOSED`.** A job merely disappearing from a
> source listing is `REMOVED_FROM_SOURCE`. Only an explicit closed/expired source
> status produces `CLOSED`; later evidence may still reconcile it (`REOPENED`).
> The freshness (`is_stale`) and evidence (`is_contradicted`) inputs are supplied
> by those layers — this function never computes them.

Idempotency: dedup keys bind volatile change types to a real stamp (the content
hash for `UPDATED`, the last-seen date for `REMOVED_FROM_SOURCE`/`REOPENED`/
`STALE`) so a genuinely new occurrence re-fires while a repeated identical
condition stays deduped. When no prior snapshot is supplied, change *types* are
derived deterministically from the record's own real cross-run columns
(`first_seen_at` / `last_seen_at` / `job_status` / `source_updated_at`).

## Trends & surges (`monitoring/trends.py`)

All counts come from real `JobRecord` observations (`first_seen_at` marks when a
canonical job was really first observed), compared across two equal windows.

- **Trend classification** (`classify_trend`) returns a `TrendStatus`. When the
  two periods together hold fewer than `min_observations` real data points it
  returns **`INSUFFICIENT_DATA`** rather than guessing a direction — the platform
  never infers a trend from a single point.
- **Hiring surge** (`detect_hiring_surge_for_company`) and **technology demand
  surge** (`detect_technology_surges_for_company`, over a tracked-technology
  vocabulary only) require **both** a meaningful absolute increase **and** a ratio
  increase over a non-trivial baseline (`evaluate_surge`), so tiny numbers
  (e.g. 1 → 3) never trigger.

> **A surge is a signal, not a commercial conclusion.** A detected surge is
> emitted as a *business signal only*. Whether it represents a commercial
> opportunity is decided by the existing opportunity logic — never here, and never
> by inventing demand.

## Tender & project monitoring (`monitoring/tenders.py`)

Operates only on REAL `TenderRecord` rows already collected/imported by the
pipeline; it **never creates a tender**. It observes newly-collected ones and
watches real closing dates:

- **`NEW_TENDER`** — tenders whose `first_seen_at` is newer than the last run. A
  missing `run_since` (first run) yields nothing — history is not retro-alerted.
- **`TENDER_CLOSING_SOON`** — only a still-open tender (open status, not
  closed/cancelled/awarded) with a known future `closing_date` inside the window
  (`closing_soon_days`, default 7). Severity is `HIGH` when closing within a day,
  else `MEDIUM`. The closing date is stamped into the dedup key so a genuinely
  different close never dedups away. Expired/cancelled tenders never alert; a
  reachable page is never assumed "open".

Consistent with the rest of the platform, a tender is classified first and is
never treated as a sales opportunity on its own.

## Source-health monitoring (`monitoring/source_health.py`)

Watches the REAL `SourceHealth` connection status (written by the existing
`collectors.connectivity` probe) and emits a `SourceHealthEvent` **once per real
transition** — never on every refresh. The "previous" status is the `new_status`
of the most recent recorded event, so a repeated identical state produces no
duplicate event (deduped by a transition-stamped `dedup_key`).

- Failure statuses (`AUTHENTICATION_FAILED`, `RATE_LIMITED`,
  `TEMPORARILY_UNAVAILABLE`, `ERROR`) raise a `SOURCE_FAILURE` finding
  (`HIGH` for auth failures, else `MEDIUM`).
- A transition back to `CONNECTED` from a prior failure raises a `SOURCE_RECOVERED`
  finding (`LOW`).

> **Source-health events NEVER produce business leads.** They are strictly
> operational alerts, carry `provenance = "OPERATIONAL"`, and bypass the business
> REAL-provenance gate precisely because they are not business data.

## Lead, company & opportunity change detection

- **Lead changes** (`monitoring/lead_changes.py`) diff a lead's state *before* and
  *after* a real recompute (score/priority, evidence confidence, conflicts,
  verified contacts, outreach readiness, stale). Score jitter below
  `min_score_delta` is ignored; a strong move (`strong_score_delta`) is `HIGH`. A
  newly-created HOT lead raises `NEW_HIGH_INTENT_LEAD`.
- **Company changes** (`monitoring/company_changes.py`) aggregate real signals:
  hiring surge/trend, new technology demand, new **verified** decision-makers, and
  newly observed project/tender business signals. Dedup keys are stamped with the
  comparison period so re-runs never duplicate.
- **Opportunity changes** (`monitoring/opportunity_changes.py`) diff two real
  `OpportunityCandidate` states; confidence must move by at least
  `MATERIAL_CONFIDENCE_DELTA` (10) to count. **Recalculation alone is not a
  change.**

## Alerting model (`notifications/`)

A `Finding` (`monitoring/findings.py`) is a detector's proposed alert-worthy fact.
The `NotificationService` (`notifications/service.py`) is the **single writer** of
`Alert` rows and applies, in order:

1. **Provenance gating (§33).** Business alert types require `provenance == "REAL"`;
   a non-REAL business finding is skipped. Operational source-health types
   (`SOURCE_FAILURE`, `SOURCE_RECOVERED`) are exempt because they are not business
   data.
2. **Preference filtering (§32).** Enabled alert types, minimum severity, and a
   `hot_leads_only` toggle that suppresses low-signal score bumps.
3. **Deduplication (§28).** The `deduplication_key` is unique — the same unchanged
   condition never re-alerts. Because volatile keys are stamped with a real value
   (score transition, closing date, period), a genuinely new occurrence still
   fires.

Each `Alert` carries type, severity, the linked entity ids (`company_id`,
`lead_id`, `opportunity_id`, `signal_id`, `tender_id`, `source_id`),
`evidence_ids`, an in-app `link`, a status lifecycle
(`NEW → ACKNOWLEDGED → DISMISSED/RESOLVED`), and `data_provenance = REAL`.

**Conservative preferences (`notifications/preferences.py`).** The single-user
`DEFAULT` preference row enables only high-value alert types
(`NEW_HIGH_INTENT_LEAD`, `LEAD_PRIORITY_INCREASED`, `HIRING_SURGE`, `NEW_PROJECT`,
`NEW_TENDER`, `TENDER_CLOSING_SOON`, `EVIDENCE_CONFLICT`, `SOURCE_FAILURE`,
`SOURCE_RECOVERED`), to avoid notification noise. Lower-signal types
(e.g. `LEAD_SCORE_INCREASED`) are off by default.

**Channels (`notifications/channels.py`).** `IN_APP` is fully implemented — the
persisted `Alert` row *is* the in-app notification. `EMAIL`, `SLACK`, and
`WEBHOOK` are **interface-only stubs**: they report `is_configured() == False` and
raise `ChannelNotConfigured` on `deliver()`. **Nothing is ever sent externally
until a channel is explicitly wired to a real, configured integration.**

## Incremental collection, idempotency, locking & retry

The scheduler runs one job at a time with strong safety guarantees
(`scheduler/service.py`):

- **Incremental collection.** Handlers reuse the existing collectors and pipeline,
  which are already idempotent — re-running updates existing leads and skips
  duplicate raw records rather than creating duplicates. Change detection then
  works from `run_since = job.last_success_at`, so only what changed since the last
  successful run is considered. A source with no credentials raises `SkipJob` and
  collects nothing; Jooble's lifetime request budget is honored (run capped to
  remaining budget, else `SkipJob`).
- **Idempotency (§21).** A scheduled run is keyed by an interval *bucket*
  (`job_name:SCHEDULE:<bucket>`); a duplicate scheduled run for the same bucket is
  recorded `SKIPPED`, not re-executed. `SchedulerRun.run_key` is unique.
- **Locking (§22).** A process-wide lock per source (`source:<id>`) or job
  prevents the same source/job running concurrently across the API thread and the
  background runner. A run that can't acquire the lock is recorded `SKIPPED`.
- **Retry policy (§23).** Errors are typed: `TransientJobError` (and any
  unexpected exception) backs off `retry_backoff_seconds` and retries up to
  `max_retries`; `PermanentJobError` (bad credentials, not-implemented,
  licensing-disabled) is **never** retried; `SkipJob` is a clean no-op recorded
  `SKIPPED`. Error strings are length-capped and credential-free.
- **Audit (§41).** Every execution writes a `SchedulerRun` with actual counters
  (`records_fetched`, `records_new`, `records_changed`, `records_removed`,
  `signals_changed`, `opportunities_changed`, `leads_changed`, `alerts_generated`),
  duration, trigger, and any error. A failed run records the error, never silence.

## Event-driven reprocessing & change-driven AI (`scheduler/reprocess.py`)

- **`run_monitoring_cycle`** — the deterministic detection + alert sweep (job
  changes, company changes, tenders, source health) with **no network calls**.
  This is the core, fully testable path, invoked by the collection and
  notification-dispatch handlers.
- **`reprocess_lead` (§34/§35)** — re-verify (and optionally re-score) a single
  lead, capture before/after `LeadState`, diff into `LeadChangeEvent`s + Findings,
  and emit alerts. Because it compares two real states it never guesses — an event
  is emitted only when values actually moved.
- **Change-driven AI re-analysis (§36)** — `should_trigger_ai` fires only on a
  meaningful lead change (priority change, score increase, conflict detected,
  evidence strengthened) at `MEDIUM`+ significance. `maybe_reanalyze_ai` then calls
  the existing `ai.service.analyze_lead`, which **reuses the context-hash cache**
  (unchanged data never re-hits a provider) and produces the **deterministic
  grounded baseline** when no provider is configured. AI failures are swallowed —
  **AI never breaks reprocessing or the scheduler**. The scheduled `AI_REANALYSIS`
  job likewise only revisits HOT/WARM leads that had a recent change event.

## APIs

Read endpoints are open (single-user app); **mutating scheduler actions require
the admin guard** (see below). No endpoint executes arbitrary code, fetches
arbitrary URLs, or exposes credentials — jobs run only registered,
source-config-bound collectors and deterministic monitoring handlers. All metrics
are actual DB/operational values.

### Scheduler control (`api/routes/scheduler.py`)

| Method & path | Purpose | Guard |
| --- | --- | --- |
| `GET /scheduler/jobs` | List scheduled jobs (seeds the default set on first read) + `scheduler_enabled`. | open |
| `GET /scheduler/jobs/{id}` | One scheduled job. | open |
| `GET /scheduler/jobs/{id}/runs` | Recent run audit for a job. | open |
| `GET /scheduler/runs` | Recent runs across all jobs. | open |
| `POST /scheduler/jobs/{id}/run` | Manually trigger a job now (`MANUAL`). | admin |
| `POST /scheduler/jobs/{id}/pause` | Pause a job. | admin |
| `POST /scheduler/jobs/{id}/resume` | Resume a paused job. | admin |

### Alert Center, preferences & dashboard (`api/routes/alerts.py`)

| Method & path | Purpose |
| --- | --- |
| `GET /alerts` | List in-app alerts (filter by status; paginated) + unread count. |
| `GET /alerts/unread-count` | Unread (`NEW`) alert count. |
| `GET /alerts/{id}` | One alert. |
| `POST /alerts/{id}/status` | Acknowledge / dismiss / resolve an alert. |
| `GET /notification-preferences` | Current alert preferences. |
| `PUT /notification-preferences` | Update alert preferences. |
| `GET /monitoring/dashboard` | Operational dashboard: pipeline counts, per-source health + latest run, jobs, recent runs, recent alerts, unread count, and a job-change-type summary — all real values, plus `scheduler_enabled` and `data_mode` (`REAL_ONLY`). |

**Example — list scheduled jobs (open):**

```bash
curl -s http://127.0.0.1:8000/scheduler/jobs | jq
```

**Example — trigger a job when an admin key is configured:**

```bash
curl -s -X POST http://127.0.0.1:8000/scheduler/jobs/1/run \
     -H "X-Admin-Key: $ADMIN_API_KEY" | jq
```

### Admin guard (`api/dependencies.py`, `require_admin`)

`require_admin` is the app's **first auth primitive**:

- If `ADMIN_API_KEY` is **unset** (the local single-user default), mutating
  scheduler actions are **allowed** — matching the existing unauthenticated app.
- If it **is set**, `POST /scheduler/jobs/{id}/run|pause|resume` require a matching
  `X-Admin-Key` header, compared with a constant-time check; otherwise the request
  is rejected `403`. The key is never logged or echoed.

## CLI (`scripts/scheduler.py`)

Drives the **same** collector/monitoring services as the API and background
runner — no duplicate ingestion logic. The existing `scripts/collect.py` manual
collection is unchanged and remains available.

```bash
python scripts/scheduler.py list             # show jobs + status (seeds defaults if empty)
python scripts/scheduler.py seed             # create the default job set (idempotent)
python scripts/scheduler.py run <job_name>   # run one job now (MANUAL trigger)
python scripts/scheduler.py tick             # run all currently-due jobs once
python scripts/scheduler.py runs [--limit N] # recent run audit history
```

`run`/`tick` execute real work: a `SOURCE_COLLECTION` job whose source is
configured will perform real collection; an unconfigured source is recorded
`SKIPPED` and collects nothing.

## Timezone & time storage

Timestamps are **stored in UTC** (`utcnow`). The scheduler's display/label
timezone defaults to **`Asia/Kolkata`** (`SCHEDULER_TIMEZONE`), matching the
Indian-IT focus; `ScheduledJob.timezone` defaults to the same. Scheduling is
interval-based (`interval_seconds`), so cadence itself is timezone-independent;
the timezone is for human-readable presentation.

## Data retention

Change events (`job_change_events`, `company_change_events`,
`lead_change_events`, `opportunity_change_events`), `source_health_events`, and
`scheduler_runs` are **append-only history** — they are **not deleted by age**.
History is preserved so trends, audits, and "what changed and when" remain
answerable. Alerts move through their status lifecycle
(`NEW → ACKNOWLEDGED → DISMISSED/RESOLVED`) rather than being deleted. No
retention/expiry job is included in this layer.

## Security notes

- **Off by default.** The background runner starts only when
  `SCHEDULER_ENABLED=true`; imports, tests, and CI never spawn threads or make
  network calls.
- **No arbitrary execution.** Jobs run only registered job-type handlers bound to
  configured collectors and deterministic monitoring — no arbitrary code, no
  arbitrary URL fetching. Collection still respects robots/ToS/rate-limits and
  per-source configuration and budgets.
- **Admin guard.** Mutating scheduler endpoints are guarded by `ADMIN_API_KEY`
  (constant-time compare, never logged) once it is set.
- **No secret leakage.** Error/message strings persisted on runs and health
  events are length-capped and credential-free; no endpoint returns credentials.
- **AI is sandboxed as before.** Change-driven AI is data/recommendation only and
  cannot execute code, fetch URLs, or send communications; failures are non-fatal.

## Real-data-only guarantee

- Detection reads only REAL records; an empty database produces **no** events and
  **no** alerts (a valid, correct state).
- The scheduler **creates no business data** — handlers reuse the existing
  real-only collectors and pipeline. A source with no credentials collects
  nothing (`SkipJob`); nothing is ever fabricated to fill a gap.
- Business alerts require `provenance = REAL`; only operational source-health
  alerts are exempt (and they never become leads).
- AI is never a source of facts here — it is change-driven, cache-bounded, and
  falls back to the deterministic grounded baseline.
- `init_db()` creates the new tables' schema only; **no rows are seeded**.

## Current status — what runs where

- **Background runner: OFF by default.** `SCHEDULER_ENABLED` is unset, so
  `settings.scheduler_active` is `False` and `api/main.py` starts **no** runner.
  Enabling docs, importing the app, or running the test suite performs **no live
  collection**.
- **On-demand paths work now.** The API (`GET /scheduler/jobs`,
  `GET /monitoring/dashboard`, the Alert Center) and the CLI operate over data
  already in the DB. Seeding registers the default job plan but runs nothing.
- **Collection still requires configuration.** Even with the scheduler enabled, a
  `SOURCE_COLLECTION` job only collects when its source is actually configured and
  permitted — otherwise it is recorded `SKIPPED`.
- **External notification channels: stubbed.** Only `IN_APP` alerts are produced;
  `EMAIL`/`SLACK`/`WEBHOOK` never send until explicitly configured.

## Testing

The deterministic core (`classify_job_change`, `classify_trend`,
`evaluate_surge`, `diff_lead`, `diff_opportunity`, `evaluate_transition`,
`SchedulerService` with an injected `now`, and `run_monitoring_cycle`) is
unit-tested without threads, sleeps, or network. The background runner is not
started by the default suite. Network-touching handlers are exercised only when a
job actually runs or via monkeypatched collection.

> **Monitoring detects change over REAL data; it is never a source of facts.**
