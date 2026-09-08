# Data Quality & Validation

This platform is **real-data-only**. This document describes the validation tooling
(`python -m app.audit …`) that proves it: what actually works, what is only
implemented, which sources are connected, and whether real data flows end-to-end
with preserved provenance.

## Audit commands

All commands read the configured database and print **actual** values. Offline
commands make no network calls; live commands are opt-in and clearly marked.

| Command | Purpose | Network? |
|---|---|---|
| `python -m app.audit validate-data` | Data-quality / integrity issues (orphans, duplicates, missing links) — actual counts | no |
| `python -m app.audit provenance` | Every business record is traceable to a real source + evidence (§3) | no |
| `python -m app.audit synthetic-data` | Synthetic **records** (DB, authoritative FAIL) + advisory runtime fabrication scan (§4) | no |
| `python -m app.audit quality` | Data-quality scorecard — actual percentages, `INSUFFICIENT_DATA` when empty (§11–19) | no |
| `python -m app.audit source-inventory` | Per-source implementation / configuration / connection / licensing (§5) | no |
| `python -m app.audit production-readiness` | Fails on critical security / real-data violations (§42) | no |
| `python -m app.audit full-report` | All sections PASS/WARN/FAIL/NOT_CONFIGURED (§51) | no |
| `python -m app.audit go-no-go` | GO only when all critical requirements pass (§52) | no |
| `python -m app.audit scorecard` | Real-data readiness summary (§53) | no |
| `python -m app.audit live-sources [--source X]` | **Real** connectivity check for configured sources (§7) | **yes** |
| `python -m app.audit live-ingestion --source X [--persist]` | Fetch a small real sample → pipeline; safe dry-run default (§8) | **yes** |
| `python -m app.audit trace-lead [--lead-id N]` | Trace one real lead → evidence → source (§21) | no |

### Status vocabulary (honesty, §54)

`IMPLEMENTED` (code present) · `CONFIGURED` (env set) · `LIVE-VERIFIED` (a real
request succeeded) · `NOT_CONFIGURED` · `NOT_IMPLEMENTED` · `REQUIRES_REVIEW` ·
`ERROR`. The tooling never infers a higher status than was actually observed —
`CONNECTED` is set only after a real `live-sources` check.

## What the audits guarantee

- **Provenance (§3):** raw records have source id + content hash; canonical jobs
  have a source reference; REAL leads have evidence **and** a source; evidence is
  traceable (URL, name, **or** domain); AI FACT claims cite evidence ids. Any
  failure is reported with an actual count.
- **Synthetic data (§4):** the **database** check is authoritative — a single
  synthetic production record is a FAIL. The runtime code scan is **advisory**
  (`REQUIRES_REVIEW`): legitimate guard/label/comment code (e.g. the "Demo data"
  provenance badge, `purge_synthetic`, the audit tooling itself) is recognised and
  excluded, so surviving hits are for human review, not an automatic block.
- **Go / No-Go (§52):** `NO-GO` on synthetic production records, missing
  provenance / broken evidence links, database-integrity issues, or critical
  production-config failures. Optional external providers being `NOT_CONFIGURED`
  do **not** block.

## Real-data snapshot (development DB, as of this validation)

These are **actual** counts from the bundled development database, produced by the
audits — not targets or fabrications. Your database will differ.

- **Source connectivity:** 1/13 (`adzuna` **LIVE-VERIFIED CONNECTED**; others
  `NOT_CONFIGURED` / `DISCOVERY_REQUIRED` / `REQUIRES_REVIEW`).
- **Raw records:** 738 · **Canonical jobs:** 738 (0 duplicate canonical jobs) ·
  **Evidence records:** 655 · **Production leads:** 318 (100% with evidence) ·
  **Companies / Signals / Opportunities / Contacts:** 0.
- **Job quality:** 100% with company / source reference / published date / content
  hash; 69.1% carry a technology tag.
- **Evidence quality:** 100% carry a source **name** (`adzuna`); 0% carry a source
  **URL** (Adzuna evidence records store the source name, not a per-record URL —
  the lead carries the source) — reported as a quality gap, not a provenance
  failure. 100% verified, 0 stale, 0 unresolved conflicts.
- **Lead quality:** 318 real leads, 100% evidence-backed, 29.6% outreach-ready.
- **Audits:** `validate-data` CLEAN · `provenance` OK · `synthetic-data` PASS (0 DB
  synthetic) · `go-no-go` **GO** (development).

> The 318 leads were produced by the per-record lead flow; the company-resolution
> flow has not been run against this data, so the `companies` table is empty. This
> is a real observation, not a defect — leads remain fully source-traceable.

## Failure-honesty guarantees

Verified by isolated tests (`tests/`): a source/AI/email/CRM outage never produces
fake fallback data; a failed send is never marked SENT and never advances a lead;
duplicate ingestion / webhook / send is idempotent; change detection emits
UPDATED/CLOSED correctly; and when no lead meets thresholds the honest result is
**"no production lead met the configured evidence and opportunity criteria"** —
thresholds are never weakened to manufacture leads (§61).
```
