# Excel Exports

LeadGenerationAgent produces two **real-data-only** Excel workbooks. Both are generated
server-side from persisted records (never a separate/fake dataset), stream in-memory (no
file stored on disk), are role-guarded (SALES/ADMIN), rate-limited, and audited. No
secrets, tokens, headers, or raw provider payloads are ever written. Text cells are
formula-injection-safe.

Empty database is a valid state: the workbook contains only the honest header row (plus a
single "No real lead data available." placeholder), never fabricated rows.

## 1. Lead Data (fixed 16-column report)

- **Endpoint:** `GET /export/excel?scope=all` → `export/excel.py`
- **Worksheet:** `Lead Data`
- **Contract (fixed — never add/remove/rename/reorder):**

| # | Column | # | Column |
|---|--------|---|--------|
| 1 | Sr No | 9 | Score |
| 2 | Company Name | 10 | Priority |
| 3 | No of Openings | 11 | Status |
| 4 | Location | 12 | Contact Number |
| 5 | Intensity | 13 | Email |
| 6 | Signal | 14 | Opportunity |
| 7 | Technology | 15 | Signal Date |
| 8 | Target POC Details | 16 | Source |

Rules: one row = one canonical company-level lead (never one row per job posting);
`No of Openings` is the canonical de-duplicated count (never a sum of syndicated
Adzuna/Jooble/ATS jobs, never the estimated team size); `Target POC Details` shows a
verified real person when available, otherwise the recommended role (never a fabricated
person); `Contact Number`/`Email` are only real source-backed values (blank otherwise);
the `Opportunity` cell combines type / staffing / est. team / urgency from the existing
Opportunity Analysis engine (no invented estimates).

## 2. Full Intelligence (complete verified intelligence)

- **Endpoint:** `GET /export/full-intelligence` → `export/full_intelligence.py`
- **Worksheet:** `Full Intelligence`
- One row per real company-level lead. Columns (grouped): Lead ID · Company Name · Legal
  Company Name · Company Number · Industry · Website · Operating Address · Registered
  Address · City · State · Country · India Presence · India Entity Type · Company Status ·
  Career URL · Contact URL · Leadership URL · LinkedIn · GitHub · Signal · Signal Summary ·
  Technology · Opening Count · Opportunity · Staffing · Estimated Team · Urgency · Score ·
  Priority · Status · **AI Profile Highlights** · **Recommended POC Role** · Target POC ·
  POC Role · **POC Status** · POC LinkedIn · POC GitHub · Work Email · Business Phone ·
  Data Trust · Contact Trust · Role Match · Email Verification · Phone Type · Phone
  Verification · Website Source · Address Source · Registered Address Source · POC Source ·
  Source · **Source URL** · **Supporting Sources** · **Evidence** · Registry URL ·
  OpenCorporates URL · POC Last Verified · Data Trust Verified · Signal Date.
- **Operating vs Registered address are kept distinct** (a registered address never
  overwrites the operating address).
- **AI Profile Highlights** are the deterministic, evidence-grounded highlights plus the
  AI insight only when an AI result was genuinely AI-generated; otherwise deterministic
  highlights only (no fabricated prose).
- **Trust columns are distinct:** Data Trust (company/signal evidence) ≠ Contact Trust
  (POC reliability) ≠ Score (commercial priority).
- Field-level provenance is preserved via the per-field Source columns + Source URL +
  Supporting Sources, following the established source priority (Official Website →
  Career/ATS → Government registry → OpenCorporates → GitHub → Wikidata → aggregators →
  paid enrichment).

## 3. Formatting

Both workbooks freeze the header row, enable autofilter, use sensible column widths,
wrap long text, format dates as `dd-mmm-yyyy`, and round scores. URLs remain readable;
long evidence/source text is wrapped, never dumped as a single JSON blob.

## 4. Real-data compliance check

`python -m app.audit export-compliance` builds the Full Intelligence workbook from the
live database and scans the actual rows for (a) demo/synthetic markers (example.com,
`john doe`, "test company", dummy, placeholder, all-zero/sequential phone numbers — all
word/phrase-anchored so a legitimate real name like "Testbook" is never rejected) and
(b) missing provenance (a real row must carry a Source / Source URL / Supporting Sources).
It exits non-zero on any violation and never mutates data (`export/compliance.py`).

## 5. UI

The Dashboard "Export Data" menu offers both workbooks (Lead Data and Full Intelligence).
Each opens a confirmation dialog showing the real record count, then downloads the
streamed `.xlsx`. Failures show an honest error — never a demo/sample fallback.
