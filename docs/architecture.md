"""Architecture and pipeline overview."""

# System design

LeadGenerationAgent is a batch pipeline with a thin HTTP API.

```
collectors → processors → intelligence → enrichment → outreach → database
```

1. **Collectors** ingest company records and public intent events (hiring, funding, RFPs, stack changes). Phase 1 uses `JsonFileCollector` and `data/sample_lead.json` only — no external scraping.
2. **Processors** drop empty names, unknown signal types, and out-of-range strengths, then persist companies and signals.
3. **Intelligence** tags each signal, estimates buying stage, scores the account 0–100, and writes an opportunity summary plus recommended sales motion.
4. **Enrichment** ranks known contacts as decision-makers, or proposes a role to target when no contact is present.
5. **Outreach** drafts a short pitch from templates. If `OPENAI_API_KEY` is set, it can optionally call OpenAI instead.

SQLite is the default store (`DATABASE_URL`). Swap the URL for Postgres when you need a shared database.

## Extending collectors

Implement `collectors.base.Collector` and return `RawCompanyRecord` objects. Point `LeadGenerationPipeline(collector=...)` at the new source, or add a FastAPI route that constructs the pipeline with that collector.
