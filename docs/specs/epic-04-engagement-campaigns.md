# EPIC-04 — Engagement & Campaign Intelligence (brief steps 4, 7)

**Objective:** Turn raw engagement numbers into comparable scores and rankings, and use
a deep agent to detect multi-post campaigns with full campaign records.

## Scope

**In:** engagement scoring, engagement rate (follower-normalized), top-N analyses,
campaign detection deep agent, persistence.
**Out:** strategy profiles, cross-competitor comparison, "why it worked" narratives
(EPIC-05).

## Interfaces & contracts

### Engagement scoring (`src/app/analysis/engagement.py`)

- `engagement_score = w_r*reactions + w_c*comments + w_s*reposts`, weights from
  `app.yaml: engagement.weights` (default 1/2/3). Missing metrics treated as 0 but
  `metrics_complete=false` recorded.
- `engagement_rate = score / followers * 100` only when profile followers present; else
  NULL (never divide by zero/None).
- Stored on `post_intelligence`.

### Rankings (`AnalysisRepo` queries, pure SQL/pandas — no LLM)

`top_posts(run_id, n)`, `top_posts_by_competitor`, `top_formats` (posts count, avg
score, avg rate, best post), `top_topics`, `top_ctas` — each returns Pydantic result
models in `src/app/schemas/analysis.py`. Format/topic tables must match brief step 5's
example shape (Format | Posts | Avg engagement | Best post).

### Campaign detection (deep agent, `src/app/analysis/campaigns.py`)

Uses `deepagents` with the `reasoning` tier via ModelRouter:
- Input files (virtual FS): per-competitor JSON of classified posts (date, topic,
  sub_topic, keywords, hashtags, format, score).
- Task: group posts into campaigns when ≥3 posts share a theme (semantic, not exact
  match — e.g. "AI in Manufacturing"/"AI-powered Manufacturing" → one campaign) within
  a bounded window; leave singletons uncampaigned.
- Output schema `CampaignRecord`: name, theme, objective, post_urls, start/end dates,
  formats, keywords, hashtags, dominant_cta, inferred_target_audience,
  total_engagement, top_post_url, performance_summary.
- Deterministic post-validation in Python: every post_url exists and belongs to the
  competitor, dates consistent, ≥3 posts, no post in two campaigns (keep
  higher-engagement campaign, log the conflict). Invalid campaigns dropped with a
  logged reason — the agent's output is never trusted blindly.
- Fake mode: a scripted deep-agent stub returns fixture campaigns so tests/demo work
  offline.

Prompts: `prompts/campaigns/campaign_cluster.{yaml,md}` (+ any sub-prompts the agent
needs, same conventions).

## Deliverables

- [x] `engagement.py` + weights config + tests (missing metrics, zero followers, rate
      NULL cases)
- [x] `schemas/analysis.py` result models
- [x] `AnalysisRepo` ranking queries + tests against seeded fixture data
- [x] `campaigns.py` deep agent + validation layer + `CampaignRepo`
- [x] `prompts/campaigns/*` + tests
- [x] Graph wiring: `score → rank → detect_campaigns` stage appended to pipeline
- [x] Tests: campaign validation drops hallucinated URLs; overlapping-campaign
      resolution; offline stub path

## Acceptance criteria

1. Scores/rates computed for all posts; a competitor without follower data yields NULL
   rates and no crashes.
2. `top_posts(run, 5)` / `(run, 10)` and per-competitor/format/topic/CTA rankings return
   correct results on a hand-computed fixture.
3. On mock data containing a seeded 4-post "AI for Manufacturing"-style cluster, the
   campaign stage (fake mode) produces one validated campaign with correct aggregates.
4. Validation demonstrably rejects a campaign referencing a nonexistent post URL.
5. `make test` offline; `make demo` includes scoring + campaigns.

## Implementation notes

- **Pipeline wiring.** There is no single unified pipeline graph object in the repo yet
  (EPIC-03 exposes `classify_posts_for_run`; stages are sequenced by `demo.py` / tests).
  Added `src/app/analysis/graph.py` with its own LangGraph `StateGraph`
  (`score → rank → detect_campaigns`) and an `analyze_run()` entrypoint, invoked from
  `demo.py` after classification — same shape as the EPIC-03 stage.
- **Deep agent.** `DeepCampaignAgent` uses `deepagents.create_deep_agent` per competitor
  with the competitor's classified posts as a virtual-FS file, and falls back to a single
  `ModelRouter.invoke` reasoning call (schema `CampaignClustering`) if the agent errors.
  Offline (`make test` / `make demo`) uses `FakeCampaignAgent`, a scripted stub that
  buckets posts by classified topic and slices `window_days` windows — zero LLM calls.
  Added `ModelRouter.chat_model_for(tier)` so the deep agent gets its chat model from the
  router module rather than instantiating one in feature code (raises in fake mode).
- **Rankings** are computed with Python aggregation over one indexed fetch of the run's
  scored posts (`AnalysisRepo.scored_rows_for_run`) rather than SQL `GROUP BY` — no LLM,
  deterministic, and directly unit-tested against a hand-computed fixture.
- **Unknown-URL handling.** A campaign that cites any post URL not present in the run is
  dropped whole (logged), per acceptance criterion 4; overlap resolution keeps the
  higher-`total_engagement` campaign and trims/drops the weaker one below `min_posts`.
- **New config** (`config/app.yaml`): `analysis.top_posts` (20),
  `analysis.top_posts_per_competitor` (5), `campaigns.window_days` (30),
  `campaigns.min_posts` (3).
