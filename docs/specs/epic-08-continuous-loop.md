# EPIC-08 — Continuous Intelligence Loop (brief step 14)

**Objective:** Make the system recurring: scheduled runs, period-over-period diffing,
emerging-topic and new-campaign detection, strategy drift alerts, and change reports.

## Scope

**In:** APScheduler integration, diff stage, change report, schedule API + UI panel,
strategy-refresh trigger.
**Out:** external notification channels (email/Slack) — design a `Notifier` interface
with a log-based default only.

## Interfaces & contracts

### Scheduler (`src/app/scheduler/`)

- APScheduler (AsyncIO scheduler) started with FastAPI lifespan; jobs persisted in a
  `schedules` table (cron expression, period_days, adapter, enabled, last_run_id).
- `POST /api/schedule` `{cron, period_days, adapter, enabled}`, `GET /api/schedule`,
  `DELETE /api/schedule/{id}`. Default suggested schedule: weekly.
- Guard: a scheduled trigger is skipped (logged) if a run is already in progress.

### Diff stage (`src/app/scheduler/diff.py`)

After a scheduled (or manually flagged) run completes, compare with the previous
completed run:

```python
class PeriodDiff(BaseModel):
    baseline_run_id: int; current_run_id: int
    new_posts: int; posts_delta_pct: float
    new_campaigns: list[str]; ended_campaigns: list[str]
    emerging_keywords: list[KeywordDelta]    # frequency growth over threshold
    fading_keywords: list[KeywordDelta]
    topic_performance_shifts: list[TopicShift]  # avg engagement delta over threshold
    format_shifts: list[FormatShift]
    profile_changes: list[ProfileChange]     # cadence/mix/best-format changes per competitor
    strategy_refresh_recommended: bool; refresh_reasons: list[str]
```

Thresholds in `app.yaml: loop` (e.g. emerging keyword = frequency ×2 with min counts;
refresh recommended when ≥N material shifts). Stored as `insights.kind = period_diff`.

### Change report + strategy refresh

- `prompts/loop/change_report.{yaml,md}` (reasoning tier): PeriodDiff → short executive
  narrative ("what changed, what to do"), stored alongside the diff.
- If `strategy_refresh_recommended`, the EPIC-06 strategy stage re-runs automatically
  for the new run and the report links old vs new strategy.
- `Notifier` interface (`notify(report)`) with `LogNotifier` default.

### Dashboard additions (extends EPIC-07)

Runs page: schedule management panel. Overview: "What changed" card when a diff exists;
emerging keywords and shifts visualized (delta bars).

## Deliverables

- [x] `schedules` table + `ScheduleRepo` + `SchedulerService` (AsyncIOScheduler) wired to
      the FastAPI lifespan + overlap guard (`RunRepo.any_in_progress`)
- [x] Schedule API routes (`POST`/`GET`/`DELETE /api/schedule`) + tests (CRUD, invalid
      cron → 422, default cron from config)
- [x] `scheduler/diff.py` + `schemas/loop.py` + tests on two seeded runs with planted
      changes (new campaign, 2× keyword, topic performance shift, profile change) — all
      detected; below-threshold noise ignored; thresholds configurable
- [x] `change_report` prompt + `scheduler/change_report.py` (LLM + deterministic
      fallback) + `Notifier` protocol / `LogNotifier`
- [x] Auto strategy refresh path (`scheduler/loop.py`) + tests (material → refresh; quiet → not)
- [x] Frontend: schedule panel (Runs page), "What changed" card + emerging-keyword /
      topic-shift delta bars (Overview page)
- [x] Docs: `README.md` "Operating the continuous loop" section; solution-design +
      CLAUDE.md cross-check pass

## Acceptance criteria

1. Creating a weekly schedule persists it and (with a short test cron) triggers a real
   run through APScheduler in an integration test.
2. Diffing two seeded runs detects exactly the planted changes; thresholds configurable.
3. A material diff flips `strategy_refresh_recommended` and regenerates strategy; a
   quiet diff does not.
4. Overlap guard: trigger during an active run skips with a logged reason.
5. Dashboard shows schedule management and the change card. `make test` offline;
   `make demo` unaffected.

## Implementation notes

- **Loop step is part of the pipeline.** `run_pipeline` runs a final `loop` stage
  (`scheduler/loop.py::run_loop_step`) after `strategy`: it diffs against
  `RunRepo.latest_completed(before_run_id=…)`, persists `period_diff` + `change_report`,
  notifies, and — if `strategy_refresh_recommended` — re-runs `run_strategy_stage` for the
  current run (recording the pre-refresh pillars in the change-report payload). No baseline
  ⇒ no-op, so `make demo` (single run) is unaffected. This means *any* run with a prior
  completed run produces a diff, not only scheduled ones — a deliberate widening of the
  spec ("scheduled or manually flagged") so two runs surface the dashboard card without a
  schedule.
- **`SchedulerService`** owns an `AsyncIOScheduler`, started from the FastAPI lifespan
  (`settings.scheduler_enabled`, default on; set `SCHEDULER_ENABLED=false` to skip — used
  by the schedule API tests). `cron` accepts a 5-field crontab **or** `@every <n>s`
  (`IntervalTrigger`) for tight cadences / the APScheduler integration test. The job body
  applies the overlap guard, creates a `trigger='scheduled'` run, sets
  `schedules.last_run_id`, and runs the pipeline in a worker thread.
- **`runs.stages`** (API) and the frontend progress bar now list six stages ending in
  `loop`.
- **Frontend** additions live in existing EPIC-07 files: `SchedulePanel` in
  `pages/Runs.tsx` (auto-hides if `/api/schedule` 404s — no longer does), "What changed"
  card + `DeltaBars` in `pages/Overview.tsx`, `diff`/`Schedule` types in `types.ts`.
- **Cross-check fixes:** `docs/solution-design.md` §6 (runs columns, `insights.kind` list
  incl. `change_report`, `schedules` table), §9 (async `POST /api/runs`, `diff` results
  route, error codes), §10 (loop mechanics); `CLAUDE.md` layout line dropped the
  never-created `graph/` dir.
