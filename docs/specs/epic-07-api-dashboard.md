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

- [ ] Routers + background pipeline execution + progress tracking on `runs` table
- [ ] Export builders (json bundle, xlsx workbook) + tests (sheet presence, row counts)
- [ ] API tests for every route incl. 404/409 and paging
- [ ] `frontend/` scaffold, typed API client (generated from route models or hand-kept
      `types.ts`), all 7 pages, loading/error states
- [ ] FastAPI static serving + SPA fallback route; Dockerfile frontend build stage
      completed; `make demo` opens a fully populated dashboard
- [ ] `README.md` updated: quickstart, screenshots section, architecture pointer

## Acceptance criteria

1. `make demo` → visit `http://localhost:8000`: all 7 pages render real data from the
   demo run without console errors.
2. Full API test suite green; xlsx export opens with one sheet per section and correct
   row counts for the demo run.
3. Starting a run from the UI shows live stage progression to completion.
4. `docker compose up` serves the same experience from a clean build.
5. `make test` (incl. API tests) offline; frontend `npm run build` succeeds in CI-like
   clean env.
