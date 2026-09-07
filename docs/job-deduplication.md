# Cross-Source Job Deduplication

The same Indian IT job can appear on Adzuna, a company career page, and other
permitted sources. For company-level hiring intelligence we must **count each
real job once** while **preserving every legitimate source reference as
evidence**.

```
Multiple source records → duplicate detection → CANONICAL JOB
                                              → source references → company intelligence
```

> Objective: "Correctly identify the same real job across multiple sources, count
> it once, and preserve every useful source reference." The goal is correctness,
> **not maximum deduplication**. Evidence verification is a later stage.

## Models (reused)

Reuses the existing `JobRecord` (canonical job) and `JobSourceReference`
(evidence). Added: `JobRecord.original_job_titles[]`, `normalized_title`,
`field_conflicts`, `deduplication_version`; `JobSourceReference.source_priority`,
`is_primary_source`, `published_at`. New `JobDuplicateCandidate` holds
MEDIUM-confidence pairs for human review.

## Architecture

```
processors/deduplication/
├── similarity.py        # token Jaccard + boilerplate reduction (no LLM/network)
├── identity.py          # DedupRecord + layered explainable matcher
├── job_deduplicator.py  # JobDeduplicationService (blocking, grouping, persistence)
├── repository.py        # review queue + canonical/source stats
└── cli.py               # python -m processors.deduplication.cli
```

Records are normalized with the Prompt-26 engine before matching, so title,
company, location, and technologies are already canonical.

## Matching strategy (layered, explainable)

Never company + title alone. In order:

1. **Same source + same external id** → 100 (a re-fetch of the exact posting).
2. **Same canonical source URL** → 95.
3. **Different external ids within the same source** → NO_MATCH — the source's own
   ids are authoritative; deduplication is *cross-source*.
4. **Company gate** (required): equal `company_domain` (strong) or equal
   `normalized_company_name`. No company match → NO_MATCH.
5. **Location**: equal city, or both remote in the same country. Different cities
   → NO_MATCH (same company + title in two cities = two jobs).
6. **Title**: exact normalized title (strong) or token similarity.
7. **Dates**: proximity bonus.
8. **Description similarity**: boilerplate-reduced token Jaccard (supporting).

Guards against over-merging (§7, §39): a differing project/team tail (e.g.
"- Payments Platform" vs "- Cloud Platform") with low description similarity →
NO_MATCH; AUTO_MERGE requires exact title OR (high title + high description
similarity).

## Match score, confidence & decision

`match_score` 0–100 → `match_confidence` HIGH/MEDIUM/LOW/NO_MATCH →
`match_decision`:

- **HIGH → AUTO_MERGE** (score ≥ 85 with strong title/description evidence)
- **MEDIUM → REVIEW** (score ≥ 62 and a plausibly-same role) → a
  `JobDuplicateCandidate` is recorded, **never auto-merged**
- **LOW / NO_MATCH** → separate canonical jobs

Thresholds/weights are configurable in `config/deduplication.py`. Every decision
is explainable (`matched_fields`, `differences`, `reason`).

## Human review

MEDIUM matches become `JobDuplicateCandidate` (PENDING) with the two record
snapshots, matched fields, and differences. `repository.py` provides
`list_pending_duplicates` / `approve_duplicate` / `reject_duplicate` (business
logic out of route handlers; no public API added yet).

## Canonical merging & source-reference preservation

The primary source is chosen by configurable `source_priority` (company career
page = 1, official ATS = 2, official API = 3, aggregator = 4) — not assumed.
`original_job_titles[]` keeps every source title; `primary_source_url` + all
`JobSourceReference`s keep every source URL/external id. **No source evidence is
deleted** (a data-loss test asserts this; raw records are never modified).

## Field conflicts (provenance, not silent choice)

When sources disagree on salary, published date, or job status, all values are
kept in `field_conflicts` per source; the primary source is used for the
canonical display value. Job status is not force-expired from one source.

## Syndication

An aggregator copy of a company-career posting is preserved as a supporting
reference (not a second hiring event). Likely syndication is inferable from the
same URL/company/date; independence is never claimed without evidence.

## Counting (critical)

Company hiring intelligence counts **canonical jobs**, not source records:

- `canonical_job_count` — unique jobs (e.g. 62)
- `source_reference_count` — source observations (e.g. 100)
- `duplicate_rate` = 1 − canonical/references
- `recent_canonical_jobs` — canonical jobs within the recent window

`repository.dedup_stats()` exposes these for the dashboard contract (Unique IT
Jobs, not Raw Job Records). Multi-city / multi-technology aggregation uses
canonical jobs (a single job can carry multiple technologies —
`jobs_with_technology` vs `technology_mentions`).

## Performance

Candidate **blocking** by normalized company name means only records for the same
company are compared; expensive description similarity runs only within a block.
Deterministic ordering makes reprocessing (`deduplication_version` "1.0.0") stable
— the same dataset always yields the same grouping.

## Limitations

- Cross-source title/description similarity is token-based (no semantic model).
- MEDIUM-confidence pairs are queued but not yet auto-remerged on approval.
- The engine reuses `JobRecord`; wiring it as the single canonical writer in the
  live pipeline (replacing the simpler ordinal dedup) is a follow-up.
- No real source is connected, so real-source deduplication was not executed.
