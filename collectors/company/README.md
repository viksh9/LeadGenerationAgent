# Company Career-Page Collector — Adding a Source

This collector reads **public** company career pages where automated access is
permitted. It respects robots.txt, terms, rate limits, and access controls, and
never executes page JavaScript. Full design: `docs/sources/company-career-pages.md`.

## Add a new company source

You rarely need any source-specific code — the generic adapter + structured-data
parsers handle most public career pages.

1. **Add a source definition** to `config/career_sources.yaml`:

   ```yaml
   - source_id: acme_careers
     company_name: Acme Corp
     company_domain: acme.com
     career_url: https://acme.com/careers
     collection_method: PUBLIC_HTML      # API | RSS | JSON | PUBLIC_HTML | CAREER_PLATFORM
     parser_type: generic
     enabled: false                      # keep disabled until verified
     robots_status: UNKNOWN
     terms_status: REQUIRES_REVIEW
     status: PLANNED
     country: IN
     industry: Software
     requires_js: false
     requests_per_minute: 6
   ```

2. **Confirm public access** — the page must be reachable without login,
   credentials, cookies, or CAPTCHA. If it needs any of these, do not collect.

3. **Confirm robots.txt and terms** — review both. If robots disallows the path,
   leave `robots_status: DISALLOWED` (it will never be collected). If terms
   restrict automated use, set `terms_status: RESTRICTED`.

4. **Select a parser** — `parser_type: generic` works when the page exposes
   JSON-LD `JobPosting` or an embedded JSON job array. JS-only pages must set
   `requires_js: true` (marked `NOT_SUPPORTED`).

5. **Add a fixture** — capture a small synthetic sample in
   `tests/fixtures/career_pages.py` (do not commit real scraped HTML).

6. **Add tests** — parser + mapping assertions in
   `tests/unit/test_career_page_collector.py` (offline, mocked).

7. **Run a dry-run**:

   ```bash
   python -m collectors.company.career_page --source acme_careers --dry-run
   ```

   It fetches, parses, and summarizes without persisting.

8. **Enable the source** — only after the dry-run works and robots/terms are
   acceptable, set `enabled: true` and, once verified end-to-end, `status:
   CONNECTED`. Never set `CONNECTED` speculatively.

## Add a new ATS adapter (advanced)

`collectors/company/adapters.py` has interface stubs for Greenhouse, Lever,
Workday, and SmartRecruiters. To implement one:

1. Subclass `CareerAdapter`, set `supported = True`, and implement `matches`,
   `start_url`, and `parse` (returning a `ParseResult`).
2. Use only documented/observable public endpoints — never guess private APIs or
   bypass authentication.
3. Register it in `_SPECIFIC_ADAPTERS` and add offline tests + fixtures.

## Safety knobs (env)

`CAREER_USER_AGENT`, `CAREER_REQUESTS_PER_MINUTE`, `CAREER_MAX_PAGES`,
`CAREER_MAX_RECORDS`, `CAREER_MAX_RESPONSE_SIZE_MB`, `CAREER_MAX_REDIRECTS`,
`CAREER_LOOKBACK_DAYS`, `CAREER_ALLOW_PRIVATE_HOSTS`, `CAREER_ALLOWLISTED_HOSTS`.
