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

- [ ] `engagement.py` + weights config + tests (missing metrics, zero followers, rate
      NULL cases)
- [ ] `schemas/analysis.py` result models
- [ ] `AnalysisRepo` ranking queries + tests against seeded fixture data
- [ ] `campaigns.py` deep agent + validation layer + `CampaignRepo`
- [ ] `prompts/campaigns/*` + tests
- [ ] Graph wiring: `score → rank → detect_campaigns` stage appended to pipeline
- [ ] Tests: campaign validation drops hallucinated URLs; overlapping-campaign
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
