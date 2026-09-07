# Frontend ↔ Backend Integration

How the React frontend and FastAPI backend work together.

## API architecture

- **Client**: `frontend/src/services/api.ts` — a single Axios instance
  (`baseURL` = `VITE_API_BASE_URL`, default `http://localhost:8000`; timeout
  `VITE_API_TIMEOUT`, default 15s; `VITE_ANALYZE_TIMEOUT` for analysis, 30s). No
  auth headers yet.
- **Services** (thin, 1:1 with routes, no business logic):
  - `services/leads.ts` — `createLead`, `analyzeLead`, `getLeads`, `getLead`,
    `updateLead`, `deleteLead`.
  - `services/health.ts` — `getHealth`.
- **Adapters** (all derivation lives here, never in JSX):
  `services/companyIntelligence.ts`, `services/opportunities.ts`,
  `services/contacts.ts`, `services/outreach.ts`, `services/analytics.ts`.

## Request / response flow

React component → TanStack Query hook → service → Axios → FastAPI route →
Pydantic schema → repository → SQLAlchemy → SQLite, and back. Frontend types in
`frontend/src/types/*` mirror the Pydantic schemas exactly; a backend contract
test (`tests/integration/test_api_contract.py`) guards the response shapes.

## React Query strategy

- Config in `lib/queryClient.ts`: `staleTime` 30s, queries retry once,
  **mutations never retry** (create/update/delete/analyze aren't idempotent),
  `refetchOnWindowFocus` off.
- Reads pass TanStack's `AbortSignal` to Axios, so stale search/filter requests
  are cancelled and can't overwrite newer results.
- One shared `GET /leads` query powers every derived view (Dashboard, Companies,
  Opportunities, Contacts, Outreach, Analytics) — no per-view/per-chart requests.

## Query keys (`hooks/useLeads.ts`)

Centralized — never scatter key strings:

```
leadKeys.all              // ['leads']
leadKeys.lists()          // ['leads','list']
leadKeys.list(params)     // ['leads','list', params]
leadKeys.detail(id)       // ['leads','detail', id]
```

## Cache invalidation

- `createLead` / `analyzeLead` → invalidate `leadKeys.all`.
- `updateLead` → invalidate `leadKeys.detail(id)` + `leadKeys.all`.
- `deleteLead` → invalidate `leadKeys.all`.

Because every derived view reads from the shared `GET /leads` query (keys under
`['leads','list',…]`), invalidating `leadKeys.all` refreshes Dashboard,
Companies, Opportunities, Contacts, Outreach and Analytics too — no full reload.

## Error handling

- Axios response interceptor → `toApiError` → normalized `{ code, message, status }`.
- `utils/apiError.ts#friendlyMessage` maps 400/401/403/404/409/422/429/500/502/
  503/504 to user-safe strings; 5xx never surface server internals.
- Mutations raise toasts (success + error) via `contexts/ToastContext`. Reads use
  each page's inline error state with Retry.
- `components/ErrorBoundary` catches render errors app-wide → "Something went
  wrong." + Reload (no stack traces in the UI).
- A non-intrusive `BackendStatus` indicator (sidebar) uses `GET /health`.

## Analyze flow

`/leads/analyze` → `AnalyzeForm` (uncontrolled; only input fields — never
score/priority/summary/action/pitch) → `POST /leads/analyze`. While pending, an
indeterminate staged indicator shows the pipeline order (no fake percentages).
On success → `AnalysisResult` with "View full lead" → `/leads/:id`. On failure
the form stays mounted (entered data preserved), an error toast shows, and
re-submitting is "Try Again".

## CORS

`config/settings.py#cors_origins` (env `CORS_ORIGINS`) allows the local dev
origins (`localhost:5173`/`3000` and their `127.0.0.1` equivalents). Configure
via env; no production domains are hard-coded.

## Environment configuration

- Backend `.env.example`: `APP_ENV`, `LOG_LEVEL`, `DATABASE_URL`, `API_HOST`,
  `API_PORT`, `CORS_ORIGINS`, `OPENAI_*`.
- Frontend `.env.example`: `VITE_API_BASE_URL`, optional `VITE_API_TIMEOUT`,
  `VITE_ANALYZE_TIMEOUT`.
- Real `.env` files are gitignored.

## Local development

```
# backend
uvicorn api.main:app --reload         # http://localhost:8000  (docs at /docs)

# frontend
cd frontend && npm run dev            # http://localhost:5173
```

Use `localhost` (or `127.0.0.1`) consistently — both origins are allowed by CORS.

## Current limitations

- No authentication (single local user); no auth headers on requests.
- Derived views are computed over the top ~100 leads (frontend aggregation), so
  analytics/company/opportunity views are labelled "based on available data".
- Company/opportunity/contact/outreach are derived from Lead data (no dedicated
  backend entities yet).

## Future authentication strategy

Add a backend auth layer (session or JWT); the Axios instance gains an auth
header interceptor and a 401 → sign-in redirect. Query keys would include the
user/tenant so caches don't cross accounts. The typed service + adapter layer
means pages won't need to change.
