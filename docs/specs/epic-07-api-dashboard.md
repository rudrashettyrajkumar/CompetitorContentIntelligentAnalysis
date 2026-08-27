# EPIC-07 — API & Dashboard (final deliverable 7)

**Objective:** Complete the FastAPI surface (runs, results, exports) and build the React
dashboard that presents the full intelligence picture.

## Scope

**In:** all API routes, xlsx/json exports, background run execution with stage
progress, React (Vite) SPA served by FastAPI, Docker multi-stage build finalized.
**Out:** scheduling endpoints/UI (EPIC-08 adds them).

## Interfaces & contracts

### API (`src/app/api/routers/`)

- `POST /api/competitors/upload` (multipart xlsx) → `IngestReport`
- `GET/DELETE /api/competitors[/{id}]`
- `POST /api/runs` body `{period_days, adapter, competitor_ids?}` → 202 + run id;
  pipeline runs in a background task; `GET /api/runs`, `GET /api/runs/{id}` →
  status + current stage + per-stage timings + errors
- `GET /api/results/{run_id}/summary` → KPI block: competitors analyzed, total posts,
  posts/week, avg engagement score & rate, top competitor, top topic, top format,
  top keywords (10), campaign count
- `GET /api/results/{run_id}/{posts|formats|topics|keywords|campaigns|profiles|cross|top-content|strategy|opportunities|calendar}`
  → the Pydantic models from earlier epics, JSON. `posts` supports paging/filter/sort
  query params.
- `GET /api/exports/{run_id}.json` → full bundle; `GET /api/exports/{run_id}.xlsx` →
  workbook with one sheet per section (openpyxl), styled headers.
- Errors: 404 unknown run, 409 run still processing for results routes, RFC7807-style
  error body.

### Frontend (`frontend/`, React 18 + Vite + TypeScript + Tailwind + Recharts)

Pages (client-side routing):
1. **Overview** — KPI tiles (summary endpoint), engagement-over-time line (per
   competitor), posts/week bar.
2. **Formats & Topics** — performance tables + bar/scatter charts (frequency vs avg
   engagement — the "frequency ≠ performance" quadrant view for keywords too).
3. **Campaigns** — campaign cards/table with drill-down to member posts.
4. **Competitors** — per-competitor strategy profile cards.
5. **Opportunities & Gaps** — white spaces, format opportunities, keyword quadrants,
   opportunity cards with hook/angle/structure.
6. **Calendar** — 30-day grid; entry detail popover.
7. **Runs** — upload Excel, start run (period + adapter selectors), run history with
   live stage progress (poll `GET /api/runs/{id}`).

Build: `npm run build` → `frontend/dist`, served by FastAPI `StaticFiles` at `/` (API
under `/api`). Dev: Vite proxy to :8000. No external CDNs (free/self-contained).

## Deliverables

- [x] Routers (`competitors`, `runs`, `results`, `exports`) + background pipeline
      execution (`app/pipeline.py`, run in a worker thread) + per-stage timings on `runs`
- [x] Export builders (json bundle, xlsx workbook via openpyxl) + tests (sheet presence,
      row counts vs. the JSON bundle)
- [x] API tests for every route incl. 404 (RFC 7807) / 409-while-processing and paging/sort/filter
- [x] `frontend/` (Vite + React 18 + TS + Tailwind + Recharts), hand-kept `types.ts` +
      typed `api.ts`, all 7 pages, loading/error/empty states
- [x] FastAPI static serving of `frontend/dist` + history-API SPA fallback; Dockerfile
      frontend build stage + self-seeding entrypoint; `make dashboard` / `docker compose up`
- [x] `README.md` updated: quickstart, dashboard/API sections, screenshots placeholder

## Acceptance criteria

1. `make demo` → visit `http://localhost:8000`: all 7 pages render real data from the
   demo run without console errors.
2. Full API test suite green; xlsx export opens with one sheet per section and correct
   row counts for the demo run.
3. Starting a run from the UI shows live stage progression to completion.
4. `docker compose up` serves the same experience from a clean build.
5. `make test` (incl. API tests) offline; frontend `npm run build` succeeds in CI-like
   clean env.

## Implementation notes

- **`POST /api/runs` is now async (202 + background pipeline)**, superseding the EPIC-02
  collect-only 200 contract. `app/pipeline.py::run_pipeline` runs collect → classify →
  analyze → map → strategy in a worker thread (`anyio.to_thread`), recording a wall-clock
  timing per stage on `runs.stage_timings`; any failure lands as `status=failed` with the
  error text. `tests/test_api_epic02.py` was updated to poll for completion.
- **`runs` table** gained `stage_timings` (JSON), `trigger` (`manual|scheduled`), and
  `competitor_ids` (the filter used). `RunRepo` gained `record_timing`, `latest_completed`,
  `any_in_progress` (the last two are groundwork EPIC-08 uses).
- **Results routes** go through `ResultsService`; `require_completed_run` raises
  `RunNotFound` → 404 or `RunNotReady` → 409, both rendered as RFC 7807
  `application/problem+json` by handlers in `app/api/errors.py`. `keywords` returns the
  cross-insight keyword matrix (the frequency-vs-performance view).
- **`/api/results/{id}/diff`** and a `ctas` section are included now so EPIC-08 only adds
  the schedule router; `main.py` already tries to include `app.api.routers.schedule` and
  tolerates its absence, and the lifespan holds an `app.state.scheduler` slot.
- **Frontend**: `frontend/` Vite build → `frontend/dist`, served by FastAPI `StaticFiles`
  at `/assets` + a catch-all that returns `index.html` for non-`/api` paths (SPA routing).
  Typed client is hand-kept (`src/types.ts` + `src/api.ts`). Recharts pushes the bundle
  ~590 KB (gzip ~170 KB) — a size warning, not an error.
- **Docker**: multi-stage (node build → python runtime); `docker-entrypoint.sh` seeds one
  `make demo` run on first boot when `runs` is empty so `docker compose up` lands on a
  populated dashboard. `docker-compose.yml` defaults to `LLM_FAKE_MODE=true`.
- **`make demo`** stays a batch script (pipeline only, no server); `make dashboard`
  (= `demo` + `frontend` + `uvicorn`) is the one-command populated dashboard.
