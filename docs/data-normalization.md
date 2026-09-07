# Data Normalization Engine

Real production data arrives from many sources, each representing the same
company, job, technology, location, or role differently. The normalization engine
produces a reliable canonical representation **without losing any original source
evidence**.

> The golden rule: **original source data is always preserved.** Normalized
> fields are stored separately, never in place of the originals.

This layer does NOT do cross-source deduplication, company merging, signal
detection, or lead scoring — those are separate stages.

## Architecture

```
processors/normalization/
├── normalizer.py          # orchestrator: normalize_job / normalize_many
├── result.py              # NormalizedJobRecord (originals + normalized + meta)
├── text.py                # safe text utils (unicode, whitespace, HTML entities)
├── title_normalizer.py    # title expansion + seniority
├── role_normalizer.py     # role taxonomy
├── technology_normalizer.py # tech aliases + categories
├── location_normalizer.py # India-first location + region
├── company_normalizer.py  # name + domain + identity confidence
├── industry_normalizer.py # industry taxonomy
├── field_normalizers.py   # employment / experience / salary / source / url
├── date_normalizer.py     # multi-format + relative dates
├── relevance.py           # is_it_relevant_job -> HIGH/MEDIUM/LOW/UNKNOWN
├── adapters.py            # source-specific adapters (adzuna, career_page)
└── cli.py                 # read-only CLI
```

Every normalizer is a **pure, deterministic function** — no network, no LLM, no
DB, no per-call queries — using preloaded mappings and compiled regex, so it is
fast enough for thousands of records.

Per the schema architecture `RawSourceRecord → NormalizedJobRecord →
CanonicalJobRecord → …`, `NormalizedJobRecord` is the in-memory normalization
stage; the canonical persisted form is the existing `JobRecord`.

## Original vs normalized data (no data loss)

`NormalizedJobRecord` keeps both, e.g.:

| Original | Normalized |
| --- | --- |
| `original_job_title` "Sr. Java Backend Engineer - Payments Platform" | `normalized_job_title` "Senior Java Backend Engineer - Payments Platform"; `role_taxonomy` JAVA_ENGINEERING; `seniority_level` SENIOR |
| `original_location` "Bangalore, Karnataka" | `normalized_city` Bengaluru, `normalized_state` Karnataka, `normalized_country` India |
| `original_technology_terms` ["Java","JAVA","SpringBoot"] | `normalized_technologies` ["Java","Spring Boot"] |
| `original_company_name` "ABC Technologies Pvt Ltd" | `normalized_company_name` "abc technologies" (for matching, not display) |
| `original_source_url` (with tracking params) | `normalized_source_url` (params stripped) |

A dedicated test asserts the originals are unchanged after normalization.

## Title taxonomy

Deterministic abbreviation expansion (Sr→Senior, Dev→Developer, Engg→Engineer,
SE→Software Engineer, Full Stack Dev→Full Stack Developer). Ambiguous titles are
not remapped (e.g. "Software Development Engineer II" is not turned into "Senior
Software Engineer"). Seniority: INTERN…EXECUTIVE, or UNKNOWN when not stated.

## Role taxonomy

Coarse, configurable codes (JAVA_ENGINEERING, CLOUD_ENGINEERING,
DEVOPS_ENGINEERING, QA_AUTOMATION, FRONTEND_ENGINEERING, DATA_ENGINEERING,
AI_ML_ENGINEERING, …). Language-specific roles win over generic ones ("Java
Backend Developer" → JAVA_ENGINEERING).

## Technology taxonomy

Alias map → canonical name + category (PROGRAMMING_LANGUAGE, FRAMEWORK, DATABASE,
CLOUD, DEVOPS, CONTAINERIZATION, MESSAGING, DATA, AI_ML, TESTING, SECURITY,
MOBILE, ERP, CRM, BI, OTHER). Word-boundary matching prevents partials ("java"
never matches inside "javascript"); "K8s"→Kubernetes, "TS"→TypeScript,
"SpringBoot"→Spring Boot, "Amazon Web Services"→AWS. Unrelated technologies are
never merged. Multi-value fields are de-duplicated case-insensitively.

## Indian locations

Configurable India city map (`config/locations_in.py`): Bangalore→Bengaluru,
Gurgaon→Gurugram, Bombay→Mumbai, Calcutta→Kolkata, HITEC City→Hyderabad, plus
state and broad region. Meaningful distinctions kept (Noida, Navi Mumbai, New
Delhi are not altered). Unknown locations stay UNKNOWN with a warning rather than
being wrongly mapped.

## Company normalization

`normalized_company_name` strips only legal suffixes (Pvt Ltd, Limited, LLP,
Inc…) — "ABC Technologies" is **not** reduced to "ABC". Domains are normalized
(protocol/www/path removed) and never guessed. A `company_identity_confidence`
(0–100) signal is produced for the future resolver; **no merging happens here**
(TCS ≠ "Tata Consultancy Services Ltd" until resolution has evidence).

## Source & URL normalization

Source names → LINKEDIN / INDEED / NAUKRI / ADZUNA / COMPANY_CAREER / … URLs are
normalized for comparison (fragment + tracking params removed, host lowercased,
trailing slash stripped) without breaking access; the original URL is preserved.

## IT relevance

`is_it_relevant_job()` → HIGH / MEDIUM / LOW / UNKNOWN from role taxonomy +
technologies + industry + text — never title alone. A single generic keyword does
not make a job HIGH; an obvious non-IT role with no tech is LOW.

## Salary & dates

Salary preserves `original_salary_text` and derives min/max/currency/period only
when explicit ("10 LPA" → 1,000,000 INR annual; "12-18 LPA" applies the unit to
both). Monthly↔yearly is never converted; ambiguous currency/period is warned.
Dates parse ISO / DD-MM-YYYY / DD/MM/YYYY (ambiguous flagged) / RFC822, plus
relative ("2 days ago", "yesterday") only against a known reference time. Nothing
is fabricated.

## Warnings & confidence

`normalization_warnings` flag unclear company, unmappable location, ambiguous
salary/currency/period, unparseable dates, etc. — risky assumptions are never
silent. `normalization_confidence` (0–100) is separate from lead score and source
confidence.

## Versioning & idempotency

`normalization_version` ("1.0.0") lets historical data be reprocessed when rules
change. Normalization is deterministic: `normalize(input) == normalize(input)`.

## Provenance

`data_provenance` (REAL/SYNTHETIC) flows through unchanged — normalization never
alters provenance.

## Source-specific rules

Adapters (`adapters.py`) add only source-specific extraction (e.g. Adzuna's
structured salary/contract_time, a career page's employment type) before the
common normalization; the common layer stays reusable.

## Security

Source content is treated as untrusted text — never executed or evaluated. HTML
is stripped to plain text only for derived fields (`text.strip_html`), while the
original field is preserved.

## Batch & CLI

`normalize_many(records)` returns results + a summary (total / normalized /
warnings / failed) and never fails the whole batch on one bad record. The
read-only CLI (`python -m processors.normalization.cli --source adzuna --limit 20
--dry-run`) loads local raw records, normalizes them, and shows examples — it
never alters source records.

## Limitations

- Title casing of glued tokens is best-effort ("ReactJS" → "Reactjs" in the
  display title, though the role/tech normalize correctly).
- The engine runs standalone; wiring it as the single source of truth for the
  canonical `JobRecord` pipeline is a planned follow-up.
- Cross-source deduplication and company merging are intentionally out of scope.
