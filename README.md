# Competitor & Content Intelligence Platform

End-to-end LinkedIn competitor intelligence: Excel competitor list → public LinkedIn
data collection → AI classification (formats, topics, keywords, campaigns) → engagement
& cross-competitor analysis → **original** content strategy, opportunities, and a
30-day calendar → React dashboard → recurring intelligence loop.

Free/open-source stack: FastAPI · LangChain · LangGraph · deepagents · SQLite ·
React/Vite. LLMs via OpenRouter free models with NVIDIA NIM → Groq fallback.

## Quickstart

```bash
make install
cp .env.example .env        # add API keys, or leave empty for offline fake mode
make test                   # offline test suite (Python)
make demo                   # end-to-end pipeline on mock data, no quota spent
make frontend               # build the React dashboard -> frontend/dist
make run                    # serve API + dashboard on http://localhost:8000

# ...or in one shot: fresh demo data + built SPA + server
make dashboard
```

Or with Docker (self-seeds a demo run on first boot):

```bash
docker compose up --build   # http://localhost:8000
```

### Dashboard

Seven pages, client-side routed, served by FastAPI from `frontend/dist`:

1. **Overview** — KPI tiles, engagement-over-time per competitor, posts/week.
2. **Formats & Topics** — performance tables + bar charts, keyword frequency-vs-performance quadrant scatter.
3. **Campaigns** — campaign cards with drill-down to member posts.
4. **Competitors** — per-competitor strategy profile cards (themes, mix, cadence, windows, positioning).
5. **Opportunities & Gaps** — white spaces, format opportunities, keyword quadrants, opportunity cards with hook/angle/structure.
6. **Calendar** — 30-day grid with an entry detail panel.
7. **Runs** — upload Excel, start a run (period + adapter), live stage progress, schedule management.

Dev mode: `cd frontend && npm run dev` (Vite on :5173, proxies `/api` to :8000).

### API

`GET /api/health` · `POST /api/competitors/upload` · `GET/DELETE /api/competitors[/{id}]`
· `POST /api/runs` (202 + background pipeline) · `GET /api/runs[/{id}]` (status + stage
timings) · `GET /api/results/{run_id}/{summary|posts|formats|topics|keywords|campaigns|
profiles|cross|top-content|strategy|opportunities|calendar|diff}` · `GET
/api/exports/{run_id}.{json|xlsx}` · `GET/POST/DELETE /api/schedule` (EPIC-08).
Results routes return **404** for an unknown run and **409** (RFC 7807 body) while a run
is still processing.

### Screenshots

_Add screenshots of the Overview, Formats & Topics, and Calendar pages here once captured
against a `make demo` run._

## Documentation

- `docs/solution-design.md` — architecture, constraints, data model
- `docs/specs/` — one spec per epic (EPIC-01 … EPIC-08)
- `CLAUDE.md` — conventions for AI-assisted epic implementation

## Status

| Epic | Status |
|---|---|
| 01 Foundation (config, LLM router, prompt registry, DB, API skeleton) | ✅ |
| 02 Input & Data Layer | ✅ |
| 03 Intelligence Layer | ✅ |
| 04 Engagement & Campaigns | ✅ |
| 05 Strategy Mapping & Cross-Competitor | ✅ |
| 06 AI Strategy Layer | ✅ |
| 07 API & Dashboard | ✅ |
| 08 Continuous Loop | ✅ |

## Operating the continuous loop (EPIC-08)

The system is built to run on a schedule, not just on demand.

- **Schedules** — `POST /api/schedule {cron, period_days, adapter, enabled}` (or the panel
  on the **Runs** page). `cron` is a standard 5-field expression; `@every 30s` interval
  form is also accepted. Jobs are stored in the `schedules` table and (re)loaded into an
  `AsyncIOScheduler` on server start. Default suggestion: weekly (`0 6 * * 1`).
- **Overlap guard** — a scheduled trigger is skipped (with a log line) if any run is
  already `pending`/`running`.
- **Period diff** — after a run completes, if a previous completed run exists the pipeline
  diffs the two: new/ended campaigns, emerging/fading keywords, topic & format engagement
  shifts, per-competitor profile changes. Stored as `insights.kind = period_diff` and
  surfaced as the **"What changed"** card + delta bars on the Overview page.
- **Change report & notify** — a short "what changed, what to do" narrative
  (`insights.kind = change_report`) is generated and pushed through a `Notifier`
  (`LogNotifier` by default; implement `notify(diff, report)` for email/Slack).
- **Auto strategy refresh** — when the count of material changes reaches
  `loop.refresh_shift_threshold`, the EPIC-06 strategy stage re-runs for the new run and
  the report records the pre-refresh pillars. All thresholds are in `config/app.yaml: loop`.

> **Compliance note:** automated scraping of LinkedIn violates LinkedIn's User
> Agreement. The Playwright adapter is disabled by default; the demo path uses
> synthetic/imported data. See `docs/solution-design.md` §7.
