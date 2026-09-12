# Official Company Career Sources

The official company career page / ATS is a **primary (Tier‑1) real-data hiring
source** — higher evidence authority than aggregators (Adzuna Tier‑2, Jooble Tier‑3),
without overriding the evidence rules. Everything here is real, source-traceable,
and SSRF-safe; nothing is fabricated (no guessed domains, board ids, URLs, or jobs).

## Real-data flow

```
REAL COMPANY (name + a real lead source URL / existing domain)
  → CompanyDomainDiscoveryService     official domain (VERIFIED/POSSIBLE/REVIEW/CONFLICT/NOT_FOUND)
  → discover_career_source            probe the company's OWN domain (SSRF-safe)
  → ATS detection (BaseATSProvider)   Greenhouse / Lever board id from the page/redirect
  → CareerPageCollector / ATS collector   real public postings
  → RawSourceRecord → normalization → CanonicalJob (deduped across Adzuna/Jooble/ATS)
  → company resolution → evidence verification → hiring signal → opportunity → lead
```

## 1. Official domain discovery (§4)

`collectors/company/domain_discovery.py` → `CompanyDomainDiscoveryService.discover(...)`.

- **Inputs:** company name, existing domain, a real source/job URL, website.
- **Never** treats an aggregator/ATS/social host (adzuna, jooble, indeed, linkedin,
  greenhouse.io, lever.co, workday, …) as the company's official domain.
- **Never** selects a domain on name similarity alone.
- **Statuses:** `VERIFIED` (the company's own real source URL / existing domain
  matches the name), `POSSIBLE`, `REVIEW_REQUIRED`, `CONFLICT` (2+ distinct strong
  domains), `NOT_FOUND`. Handles two-level TLDs (e.g. `wipro.co.in`).
- Optional `verify=True` performs one SSRF-safe homepage fetch to confirm the
  company name appears (upgrades POSSIBLE→VERIFIED); best-effort, never fabricates.

## 2. Career-page discovery + verification (§5/§6)

`collectors/company/career_source_discovery.py` → `discover_career_source(...)`
probes only the company's own domain (`/careers`, `/jobs`, homepage), makes real
SSRF-safe requests, and verifies ownership when the ATS identifier is found on the
company's own careers page (link) or via a redirect from it. Discovery methods:
`careers_page_link`, `careers_page_redirect`. Uncertain → not verified (the caller
persists `DISCOVERY_REQUIRED` / `REVIEW_REQUIRED`).

## 3. ATS detection (pluggable) (§7/§11)

`collectors/company/ats.py` → `BaseATSProvider` with `detect()` + `build_collector()`,
and an `ATS_PROVIDERS` registry. **Implemented (documented public interfaces):**

| ATS | Public endpoint | Identifier | Status |
|---|---|---|---|
| **Greenhouse** | `boards-api.greenhouse.io/v1/boards/{board}/jobs` | board token | IMPLEMENTED |
| **Lever** | `api.lever.co/v0/postings/{site}?mode=json` | site handle | IMPLEMENTED |

Other ATS (Workday, SAP SuccessFactors, SmartRecruiters, iCIMS, Ashby) are
**NOT_IMPLEMENTED** — the plugin architecture exists, but an adapter is added only
when its public interface is documented and permitted. No private APIs, no CAPTCHA/
anti-bot bypass, no recruiter credentials.

## 4. Generic career pages

When no supported ATS is detected, the generic `CareerPageCollector` extracts
public content in priority order: JSON‑LD `JobPosting` → public structured JSON →
documented public endpoint → permitted HTML. Only public, business-relevant data
is collected (§52). Robots/terms are respected (`collectors/company/robots.py`);
if access is not permitted → `REQUIRES_REVIEW` / `NOT_SUPPORTED`, never bypassed.

## 5. Pipeline integration

Career/ATS jobs use the SAME pipeline: raw persistence (immutable, full provenance
— company, official career URL, source URL, ATS provider, board id, timestamps,
content hash, `provenance_type=REAL`), normalization, **cross-source dedup** (one
`CanonicalJob`, multiple source references — official + Adzuna + Jooble never count
as 3 jobs), company resolution, evidence verification, hiring aggregation +
intensity, signals, opportunity, lead. Official-source authority raises **evidence
confidence** but not lead score / commercial intent (§57).

## 6. APIs & frontend

- `GET /career-sources`, `GET /career-sources/{id}`, `GET /companies/{id}/career-sources`
- `POST /companies/{id}/discover-career-source` (runs domain discovery when the
  company has no known domain, then career/ATS discovery + verification)
- `POST /career-sources/{id}/check` (real connectivity), `POST /career-sources/{id}/collect`
- **Company Details** shows the official career source (URL, ATS, status, last
  checked/success, jobs, evidence confidence) with Check/Collect actions.

## 7. Health, scheduler, failure behaviour

Per-source health (checks/success/failure/records) on `CompanyCareerSource`.
Scheduler can refresh sources on a configurable cadence (high-value companies more
often); company sites are rate-limited/backed-off — never hammered. **Source
failure never deletes prior real data** — the failure is recorded and retried;
recovery is re-checked without creating duplicates. Change detection (Prompt 38)
emits NEW/UPDATED/CLOSED/REMOVED_FROM_SOURCE/REOPENED/UNCHANGED.

## 8. Terms, licensing & security

Only public postings; robots + site terms respected; SSRF protection blocks
localhost/private/loopback/link-local/metadata/`file:`/`ftp:` and non-HTTP(S).
Requests are timed out, size-limited, and redirect-controlled. Greenhouse/Lever
public postings require no credentials and expose no candidate/recruiter data.

## Data dictionary (career-source entities)

`CompanyCareerSource` (company_id, company_name, ats_provider, board_identifier,
careers_url, discovery_method, status, enabled, last_checked_at, last_success_at,
last_error, data_provenance) · `Company` · `JobRecord` (canonical) ·
`JobSourceReference` (per-source, incl. career/ATS) · `EvidenceRecord` ·
`BusinessSignal` · `OpportunityCandidate` · `Lead`.

## Live testing

Opt-in only: `RUN_LIVE_SOURCE_TESTS=true` runs controlled checks against a real
career page / Greenhouse / Lever source when configured. Normal tests use no
network. Live runs never insert data into production automatically.
