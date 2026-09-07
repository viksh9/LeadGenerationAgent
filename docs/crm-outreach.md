# CRM & Outreach Lifecycle

This layer turns a scored, evidence-backed **lead** into a managed **sales
relationship**: a validated lifecycle state machine, an internal CRM (activities,
timeline, pipeline), evidence-grounded outreach drafting, a safe email send flow,
secure inbound webhooks, follow-up tasks, and honest analytics. It sits *over* the
real, already-verified data produced by the collection/verification/scoring
pipeline.

> **Outreach acts on REAL data and REAL events only; it is never a source of
> facts.** It cannot invent a company, person, contact, reply, or number. Every
> factual claim in a draft maps to a real evidence record; every "contacted",
> "replied", and "meeting" state is backed by a real provider event or an explicit,
> audited human action.

> **No message is ever sent automatically, and none can be sent at all in the
> default configuration.** Sending requires (1) a configured email provider AND
> (2) an explicit human approval of the specific draft. Out of the box no provider
> is configured, the CRM is `INTERNAL`, and webhooks are rejected until
> `WEBHOOK_SECRET` is set. Drafts can be generated and approved, but not sent.

## Design philosophy

- **Real-data-only.** Every CRM activity, opportunity, and analytic is computed
  from real database records (`data_provenance = REAL`). An empty database is a
  valid state — the CRM, pipeline, and analytics simply show nothing, never
  fabricated activity, revenue, or conversion.
- **Event-gated truth.** A lead is never *claimed* to have been contacted, to have
  replied, or to have met unless a real event backs it (a provider-confirmed send,
  a real inbound reply, a recorded meeting) or a human sets it explicitly with a
  reason. See [Lead lifecycle](#lead-lifecycle-state-machine).
- **Human-in-the-loop for anything outbound.** The system drafts; a human approves;
  only then, and only through a configured provider, does anything send. There is
  no bulk send and no auto-send.
- **Deterministic by default.** Message generation reuses the existing
  deterministic pitch generator; reply classification is a deterministic keyword
  classifier. AI, when configured, may only refine wording — it is bound to the
  same evidence/text and can never introduce a new factual claim.
- **Everything is audited.** Every status change, draft action, send, and provider
  event writes an immutable `AuditLog` row plus a CRM activity — who/what/when/
  old/new/source/reason — with credentials never written.

## Where it sits

```
LEAD (scored, evidence-backed)                        ← from the existing pipeline
  → LIFECYCLE (crm/lifecycle.py)      validated, event-gated state machine + history
  → CRM ACTIVITIES (crm/activities.py)  real events (note/call/meeting/send/reply)
  → OUTREACH DRAFT (outreach/service.py)  evidence-grounded, human-reviewed draft
      → APPROVE (human)               required before any send
      → SEND (outreach/send.py)       verified email + configured provider + limits
          → provider CONFIRMS  → mark SENT → advance lead to CONTACTED (event-gated)
  → WEBHOOK (crm/webhooks.py)         signed provider events: delivered/bounce/reply
      → REPLY (outreach/reply.py)     record reply → advance to REPLIED → review task
  → PIPELINE (crm/pipeline.py)        managed SalesOpportunity + stages
  → FOLLOW-UPS (crm/followups.py)     tasks from real conditions (never busy-work)
  → ANALYTICS (crm/analytics.py)      honest funnel / conversion / pipeline value
```

The deterministic pipeline stays authoritative for source data, normalization,
resolution, dedup, evidence verification, signal classification, lead score,
opportunity type, and contact verification. This layer manages the *relationship*
on top of it and never re-derives those facts.

## Lead lifecycle state machine

`LeadLifecycleService` (`crm/lifecycle.py`) owns every status change. Transitions
are **explicit and validated** against an allow-list; an illegal jump raises a
`validation_error`. `LeadStatus` values:

`NEW → RESEARCHED → OUTREACH_READY → CONTACTED → REPLIED → MEETING → QUALIFIED →
PROPOSAL → WON`, plus the off-funnel terminals `LOST`, `NURTURE`, and
`DISQUALIFIED`. A same-state transition is a no-op (no history row is written).

### Event-gating (the core guarantee)

Three statuses assert that a real interaction happened and are therefore
**event-gated** — they cannot be reached automatically without a real event
source:

| Target status | Required real event source | Set automatically by |
| --- | --- | --- |
| `CONTACTED` | `SEND_CONFIRMED` | a provider-confirmed send (`outreach/send.py`) |
| `REPLIED` | `PROVIDER_REPLY` | a real inbound reply (`outreach/reply.py`) |
| `MEETING` | `MEETING_RECORDED` | a recorded meeting event |

An automated caller that tries to advance a lead to one of these without the
matching `source` is rejected. A **human** may still set them explicitly
(`changed_by="human"` with a reason) — that action is fully audited. This is why
the analytics funnel is honest: a lead is only ever "contacted" because something
real happened.

### Status history + audit log

Every accepted transition writes three things in one unit of work:

1. an immutable `LeadStatusHistory` row (`old_status`, `new_status`, `changed_by`,
   `reason`, `source`, timestamp),
2. a `STATUS_CHANGE` CRM activity (system vs human is recorded), and
3. an `AuditLog` entry (`crm/audit.py`).

History is append-only and is exposed at `GET /leads/{id}/status-history`.

## CRM activities

`CRMActivityService` (`crm/activities.py`) records **real events only**: human
notes/calls/meetings, system events (e.g. status changes), and provider-confirmed
sends/replies/deliveries. Key rules:

- `status = SENT` only when a real provider confirms it; `REPLIED`/`COMPLETED`
  only when a real event is recorded — the service never fabricates activity.
- Activities are **deduplicated by `(source, external_id)`**, so provider
  re-delivery of the same event never creates a duplicate row (idempotent).
- Every activity carries `data_provenance = REAL`.

Timelines are served per lead (`GET /leads/{id}/timeline`) and merge CRM
activities (human vs system) with monitoring `LeadChangeEvent`s into one
chronological view.

## Outreach drafting (evidence-grounded)

`OutreachService.generate_draft` (`outreach/service.py`) produces a
human-reviewable **draft**, never a sent message:

- It collects the lead's **real evidence records** and stamps their ids onto the
  draft (`evidence_ids`), so every factual claim maps back to real evidence.
- The message body reuses the existing deterministic **pitch generator**
  (`outreach/pitch_generator.py`), which only references real supplied numbers and
  never asserts a new fact.
- The recipient is a **verified business contact** resolved from the company
  (`outreach/contacts.py`) — never fabricated, never a guessed `first.last@` address.
- **Grounding gate:** with no supporting evidence the draft stays in status
  `DRAFT` (flagged, not review-ready) and **cannot be approved**. With evidence it
  becomes `READY_FOR_REVIEW`.

Draft status lifecycle (`OutreachDraftStatus`):

```
DRAFT ─┬─(evidence)→ READY_FOR_REVIEW ─(human approve)→ APPROVED ─(send OK)→ SENT
       └─(no evidence, cannot approve)                    │              └─(send fail)→ FAILED
                                                          └─(edit)→ back to READY_FOR_REVIEW
CANCELLED is reachable from any non-SENT state.
```

Editing an already-`APPROVED` draft returns it to `READY_FOR_REVIEW` so it must be
re-approved before it can be sent. Approval assigns an idempotency key used to
protect the subsequent send.

### AI enhancement (optional, off by default)

When an AI provider is configured, an optional enhancement step may improve only
wording/clarity/CTA. Its output is bound to the **same evidence** and cannot
introduce a new factual claim; drafts are stamped `ai_generated=false` unless AI
actually ran. With no provider configured (the default), drafting is fully
deterministic.

## Email provider abstraction

`crm/providers/email_provider.py` defines `BaseEmailProvider` and one real
implementation:

- **`SMTPEmailProvider`** — a real sender over the **stdlib `smtplib`** (no
  third-party SDK). It is `is_configured()` only when `SMTP_HOST` and `EMAIL_FROM`
  are set; it uses STARTTLS when `SMTP_USE_TLS=true` and logs in only when a
  username+password are both present. Its `probe()` performs a real `NOOP`
  connection and returns `CONNECTED` / `ERROR` / `NOT_CONFIGURED`.
- **SendGrid / Microsoft Graph / Gmail API** — recognised provider *names* but
  **not implemented**. `build_email_provider` returns `None` for them, so the app
  reports `NOT_CONFIGURED` rather than pretend to send.

`build_email_provider()` returns `None` unless a provider is actually configured —
so the send flow **physically cannot send without configuration**. Credentials
come from settings/env only and are never logged.

### Send safety (`outreach/send.py`)

`send_draft` enforces, strictly in order:

1. **Idempotency short-circuit** — a draft already `SENT` returns unchanged (no
   duplicate send).
2. **Approval** — only an `APPROVED` draft can be sent.
3. **Channel** — only `EMAIL` is implemented; `LINKEDIN`/`CALL` must be handled
   manually (never auto-sent).
4. **Verified recipient** — when `OUTREACH_REQUIRE_VERIFIED_EMAIL=true` (default),
   the contact must have a source-verified business email; otherwise the send is
   refused. The address is always format-validated.
5. **Provider configured** — `build_email_provider` must return a real provider,
   else `NOT_CONFIGURED` → refused.
6. **Daily cap + per-minute rate limit** — `EMAIL_DAILY_LIMIT` and
   `EMAIL_RATE_PER_MINUTE` (never mass-sends). Exceeding either is refused, not
   queued.
7. **Idempotency lock** — a per-draft in-process lock plus a re-check under the
   lock defeats double-clicks / retries / restarts.

**Provider-confirmed `SENT` only.** The draft is marked `SENT`, a `SENT` CRM
activity is logged, an audit row is written, and the lead is advanced to
`CONTACTED` (via the event-gated lifecycle with `source="SEND_CONFIRMED"`) **only
when the transport confirms the send**. On any failure the draft becomes `FAILED`,
no lead advances, a `SEND_FAILED` audit row is written, and nothing is fabricated.

## Webhooks (signed, replay-safe, deduped)

`crm/webhooks.py` ingests **real provider events only** (delivery, bounce, reply)
via `POST /webhooks/email/{provider}`.

- **HMAC signature.** `verify_signature` computes a constant-time HMAC-SHA256 over
  `"{X-Timestamp}.{raw body}"` keyed by `WEBHOOK_SECRET`, and compares it to the
  `X-Signature` header (a leading `sha256=` prefix is tolerated).
- **Timestamp / replay window.** The request is rejected if
  `|now − X-Timestamp| > WEBHOOK_TOLERANCE_SECONDS` (default 300s).
- **Fail closed.** With `WEBHOOK_SECRET` unset, *every* request fails verification —
  unsigned payloads are never trusted.
- **Recorded + deduped.** Each event is stored as a `WebhookEvent` and
  **deduplicated by `(provider, provider_event_id)`**; a repeat delivery returns
  `duplicate` and is not reprocessed. An invalid signature is stored with status
  `INVALID` and **not processed**.

### Reply handling + deterministic classification

On a `reply`/`inbound` event, `outreach/reply.py::record_reply`:

1. matches the lead/contact from the outbound message's provider id/thread id
   (never guesses beyond real provider identifiers),
2. records a deduped `EMAIL_REPLY` CRM activity,
3. advances the lead to `REPLIED` (event-gated, `source="PROVIDER_REPLY"`),
4. **classifies the reply deterministically** (`outreach/ai_reply.py`) into a
   `ReplyClassification` (`POSITIVE`, `NEGATIVE`, `INTERESTED`,
   `REQUEST_MORE_INFO`, `MEETING_REQUEST`, `NOT_NOW`, `NOT_RELEVANT`,
   `OUT_OF_OFFICE`, `UNKNOWN`) — always carrying the matched **quote/snippet from
   the actual message**, so the label can never be fabricated, and
5. creates a `REVIEW_REPLY` follow-up task so a human reviews every real reply.

Delivery/bounce events update the matching draft's activity trail; a bounce on a
`SENT` draft records the provider failure.

## Follow-up tasks + scheduler conditions

`FollowUpService` (`crm/followups.py`) creates tasks **from real conditions only** —
never invented busy-work — all deduplicated by `dedup_key`. It **never sends
anything**; it only creates review/reminder tasks for a human. The scheduler-facing
`generate_from_conditions` derives tasks from:

- **No reply after a send** — a confirmed `SENT` draft with no real inbound reply
  after the window (default 3 days) → a `FOLLOW_UP` task.
- **Tender closing soon** — a real, open `TenderRecord` with a known future
  `closing_date` inside the window (default 7 days) → a `CHECK_TENDER_DEADLINE`
  task.
- **Lead priority increased** — a real `LeadChangeEvent` of type
  `PRIORITY_CHANGED` since the last run → a `REVIEW_LEAD` task.

These run under the existing monitoring scheduler
([docs/monitoring-scheduler.md](monitoring-scheduler.md)) when it is enabled, or on
demand — the scheduler is **off by default**, so no follow-ups are generated in the
background unless `SCHEDULER_ENABLED=true`.

## Sales pipeline

`SalesPipelineService` (`crm/pipeline.py`) manages `SalesOpportunity` records
across the `SalesStage` ladder: `IDENTIFIED → RESEARCHED → OUTREACH_READY →
CONTACTED → ENGAGED → QUALIFIED → DISCOVERY → PROPOSAL → NEGOTIATION → WON`, with
`LOST`/`NURTURE` off-ladder. Real-data rules:

- **`estimated_value` is never inferred.** It exists only when a user enters it
  (`value_source="USER"`) or it is evidence-supported (`value_source="EVIDENCE"`);
  otherwise `value_source="NOT_AVAILABLE"` and the value stays null. Attempting to
  set a value without a legitimate source is rejected.
- **`probability` is a sales judgement**, distinct from `lead_score` — it is never
  auto-derived from the score.
- An analytical `OpportunityCandidate` can be **promoted** to a managed opportunity
  (`/opportunity-candidates/{id}/promote`); no monetary value is invented in the
  process.
- Stage changes are validated and audited; `WON`/`LOST` are outcomes callers should
  gate behind human approval.

## Internal CRM & external CRM extension points

`crm/providers/crm_provider.py` defines `BaseCRMProvider`. Only
**`InternalCRMProvider`** is implemented: **the local database IS the CRM** — the
source of truth for internal lead/sales state, always available, no external
calls. Its status is `CONNECTED` because the local store is always reachable.

External connectors (Salesforce, HubSpot, Zoho, Pipedrive) are the documented
**extension point** but are **not implemented** in this phase. `build_crm_provider`
returns the internal provider even when an external `CRM_PROVIDER` name is set — it
never fabricates an external connection. The supporting schema exists for when a
real connector is added:

- `crm_sync_records` (`CRMSyncRecord`) — the local↔external id mapping
  (`provider`, `entity_type`, `entity_id`, `external_id`, `sync_status`,
  `last_synced_at`, `direction`), unique per `(provider, entity_type, entity_id)`
  to prevent duplicate external records.
- `sync_conflicts` (`SyncConflict`) — a detected divergence between local and
  external state. **Conflicts are never silently overwritten**: each carries a
  `SyncResolution` of `LOCAL_WINS` / `EXTERNAL_WINS` / `REVIEW_REQUIRED` (default
  `REVIEW_REQUIRED`) and must be resolved explicitly.

## Honest analytics

`crm/analytics.py::compute_crm_analytics` computes **every number from real
records** and refuses to fabricate:

- **Conversion rates** are returned only when the denominator has real events;
  otherwise the metric is the string **`INSUFFICIENT_DATA`** (denominators are
  never invented). The funnel (`contact_rate`, `reply_rate`, `meeting_rate`,
  `qualification_rate`, `proposal_rate`, `win_rate`) is measured "at or beyond" each
  real lead status — honest precisely because statuses only advance on real events.
- **Pipeline value** sums only opportunities whose value has a legitimate source
  (`USER`/`EVIDENCE`). If none exist, the value is **`NOT_AVAILABLE`** — revenue is
  never inferred from job counts or lead scores.
- `real_contacted` / `real_replies` / `real_meetings` are counted from real CRM
  activities, not from status labels alone.

## Security: RBAC, rate limiting, readiness

- **RBAC (`api/security.py`).** Header-based and additive. When `ADMIN_API_KEY` is
  **unset**, every request resolves to `ADMIN` — the app stays fully open locally,
  unchanged. When it **is set**, a valid `X-Admin-Key` grants `ADMIN`; otherwise the
  role comes from the `X-Role` header (`SALES` / `RESEARCHER` / `VIEWER`, default
  `VIEWER`). Read endpoints allow `VIEWER`+; mutations require `SALES` (or `ADMIN`).
  This is a **single shared admin key + role header**, *not* a multi-user auth
  system — there are no user accounts, sessions, or passwords.
- **Rate limiting.** An in-process rolling-window limiter guards abusable endpoints:
  outreach send (30/min process-wide), webhooks (120/min), plus the send flow's own
  per-minute cap and daily cap. It is per-process, not distributed.
- **Readiness (`GET /health/ready`).** Verifies the **database** (the only required
  dependency). Optional providers (email/CRM/AI) and the scheduler are reported for
  visibility but **never flip readiness** — a missing optional provider is a valid,
  healthy state.
- **Error envelope.** All errors serialize as `{"error": {"code", "message"}}`
  (`config/exceptions.py` + the API error handlers).

## APIs

Error responses use the `{"error": {"code", "message"}}` envelope. Read endpoints
allow any role; mutations require `SALES`/`ADMIN`; webhooks are public but
cryptographically verified. All examples assume `http://127.0.0.1:8000`.

### Lifecycle, activities & timeline (`api/routes/crm.py`)

| Method & path | Purpose | Role |
| --- | --- | --- |
| `POST /leads/{id}/transition` | Human status change (validated + audited). | SALES |
| `GET /leads/{id}/status-history` | Immutable status history. | VIEWER |
| `GET /leads/{id}/next-best-action` | Deterministic NBA from real state. | VIEWER |
| `GET /leads/{id}/activities` | CRM activities for a lead. | VIEWER |
| `POST /activities` | Log a manual CRM activity. | SALES |
| `GET /leads/{id}/timeline` | Merged activities + change events. | VIEWER |

### Sales pipeline (`api/routes/crm.py`)

| Method & path | Purpose | Role |
| --- | --- | --- |
| `GET /sales-opportunities` | List managed opportunities (filters). | VIEWER |
| `GET /pipeline/board` | Board grouped by stage. | VIEWER |
| `POST /sales-opportunities` | Create an opportunity. | SALES |
| `POST /sales-opportunities/{id}/stage` | Change stage (human-approved). | SALES |
| `POST /opportunity-candidates/{id}/promote` | Promote an analytical candidate. | SALES |
| `GET /crm/analytics` | Honest analytics (INSUFFICIENT_DATA / NOT_AVAILABLE). | VIEWER |

### Follow-ups (`api/routes/crm.py`)

| Method & path | Purpose | Role |
| --- | --- | --- |
| `GET /follow-ups` | List follow-up tasks (filters). | VIEWER |
| `POST /follow-ups/{id}/status` | Update a task's status. | SALES |

### Outreach (`api/routes/outreach.py`)

| Method & path | Purpose | Role |
| --- | --- | --- |
| `GET /outreach/drafts` · `/drafts/{id}` | List / get drafts. | VIEWER |
| `POST /outreach/drafts` | Generate an evidence-grounded draft. | SALES |
| `PUT /outreach/drafts/{id}` | Edit a not-yet-sent draft. | SALES |
| `POST /outreach/drafts/{id}/approve` | **Human approval** (required to send). | SALES |
| `POST /outreach/drafts/{id}/cancel` | Cancel a draft. | SALES |
| `POST /outreach/{id}/send` | Send an APPROVED draft (provider-confirmed). | SALES |
| `GET /outreach/providers/status` | Truthful email/CRM status (no secrets). | VIEWER |

### Webhooks (`api/routes/webhooks.py`)

| Method & path | Purpose | Auth |
| --- | --- | --- |
| `POST /webhooks/email/{provider}` | Ingest a signed delivery/bounce/reply event. | HMAC signature + timestamp |

### Examples

List drafts and generate one for a lead:

```bash
curl -s http://127.0.0.1:8000/outreach/drafts | jq
curl -s -X POST http://127.0.0.1:8000/outreach/drafts \
     -H 'Content-Type: application/json' \
     -d '{"lead_id": 1, "channel": "EMAIL"}' | jq
```

Check the truthful provider status (out of the box: email `NOT_CONFIGURED`):

```bash
curl -s http://127.0.0.1:8000/outreach/providers/status | jq
```

Approve then send (send only succeeds when a provider is configured and the
recipient has a verified business email):

```bash
curl -s -X POST http://127.0.0.1:8000/outreach/drafts/5/approve | jq
curl -s -X POST http://127.0.0.1:8000/outreach/5/send | jq
```

Transition a lead by hand (with an admin key configured):

```bash
curl -s -X POST http://127.0.0.1:8000/leads/1/transition \
     -H "X-Admin-Key: $ADMIN_API_KEY" -H 'Content-Type: application/json' \
     -d '{"new_status": "NURTURE", "reason": "Following up next quarter"}' | jq
```

**Signing a webhook.** The signature is HMAC-SHA256 over `"{timestamp}.{body}"`
keyed by `WEBHOOK_SECRET`; the request must include `X-Timestamp` and
`X-Signature`:

```bash
SECRET="$WEBHOOK_SECRET"
TS=$(date +%s)
BODY='{"event_id":"evt_123","event_type":"reply","message_id":"msg_1","body":"Sounds good, let us set up a call"}'
SIG=$(printf '%s.%s' "$TS" "$BODY" | openssl dgst -sha256 -hmac "$SECRET" | awk '{print $2}')

curl -s -X POST http://127.0.0.1:8000/webhooks/email/generic \
     -H "X-Timestamp: $TS" -H "X-Signature: sha256=$SIG" \
     -H 'Content-Type: application/json' -d "$BODY" | jq
```

With no `WEBHOOK_SECRET` set, this request is rejected (fail closed) and stored as
`INVALID`.

## Audits & operations

Two audit commands operate on the real configured database and report actual
counts (they never insert or fabricate):

```bash
python -m app.audit validate-data                 # data-quality issues (actual counts)
python -m app.audit validate-data --json          # machine-readable
python -m app.audit validate-data --fail-on-issues  # exit 1 if any issue

python -m app.audit production-readiness           # real-data/security gate
python -m app.audit production-readiness --json
```

`validate-data` reports (among others) records missing provenance, synthetic
records, REAL leads without evidence, orphaned CRM activities/opportunities, and
duplicate canonical jobs. `production-readiness` fails (exit 1) on any critical
real-data/security violation. See
[docs/production-readiness-checklist.md](production-readiness-checklist.md).

## Current status — what is live

- **Email: NOT configured by default.** No `EMAIL_PROVIDER` is set, so
  `GET /outreach/providers/status` reports `NOT_CONFIGURED`. Drafts can be
  generated, edited, and **approved**, but **cannot be sent** until SMTP (the only
  implemented provider) is configured.
- **CRM: `INTERNAL`.** The local database is the CRM. No external CRM connector is
  implemented; naming an external provider still uses the internal store.
- **Webhooks: require `WEBHOOK_SECRET`.** Until it is set, all webhook requests
  fail closed and are recorded `INVALID`.
- **No message is ever auto-sent.** Every send is one explicit, human-approved,
  rate-limited action; there is no bulk or background send. The scheduler (which
  only generates *tasks*, never messages) is off unless `SCHEDULER_ENABLED=true`.
- **RBAC is a single shared key + role header**, not a multi-user auth system.

## Real-data-only guarantee

- Every CRM activity, opportunity, and analytic is derived from real records
  (`data_provenance = REAL`); an empty database produces empty, honest output —
  never fabricated activity, revenue, or conversion.
- `CONTACTED` / `REPLIED` / `MEETING` require a real event source or an explicit,
  audited human action — the funnel cannot be inflated with imaginary interactions.
- Outreach drafts are grounded in real evidence (`evidence_ids`); an ungrounded
  draft cannot be approved. The pitch generator and reply classifier are
  deterministic; AI (if configured) may only refine wording and can add no fact.
- Sends are marked `SENT` **only** on a real provider confirmation; failures never
  advance a lead or fabricate a result. Webhooks are HMAC-verified, replay-checked,
  and deduped — arbitrary payloads are never trusted.
- Deal value and conversion rates are `NOT_AVAILABLE` / `INSUFFICIENT_DATA` rather
  than inferred. `init_db()` creates these tables' schema only; no rows are seeded.
