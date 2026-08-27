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

- [ ] `schedules` table + repo + APScheduler wiring with lifespan + overlap guard
- [ ] Schedule API routes + tests (create/list/delete, invalid cron rejected)
- [ ] `diff.py` + schemas + tests on two seeded runs with planted changes (new campaign,
      2× keyword, topic performance shift) — all detected; below-threshold noise ignored
- [ ] `change_report` prompt + generation + `Notifier`/`LogNotifier`
- [ ] Auto strategy refresh path + test
- [ ] Frontend: schedule panel + "What changed" card + delta visuals
- [ ] Docs: `README.md` section on operating the loop; solution-design cross-check pass
      (fix any drift between docs and implementation across all epics)

## Acceptance criteria

1. Creating a weekly schedule persists it and (with a short test cron) triggers a real
   run through APScheduler in an integration test.
2. Diffing two seeded runs detects exactly the planted changes; thresholds configurable.
3. A material diff flips `strategy_refresh_recommended` and regenerates strategy; a
   quiet diff does not.
4. Overlap guard: trigger during an active run skips with a logged reason.
5. Dashboard shows schedule management and the change card. `make test` offline;
   `make demo` unaffected.
