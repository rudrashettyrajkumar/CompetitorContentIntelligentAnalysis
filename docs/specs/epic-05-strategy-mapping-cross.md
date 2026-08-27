# EPIC-05 — Competitor Strategy Mapping & Cross-Competitor Intelligence (brief steps 8–10)

**Objective:** Move from data to intelligence: per-competitor strategy profiles,
cross-competitor comparison (white spaces, saturation, format opportunities), and the
Top-20 content report with "why it worked" analysis.

## Scope

**In:** strategy profiles, cross-competitor analytics, top-content report + LLM
explanations, keyword frequency-vs-performance matrix.
**Out:** our-company strategy generation (EPIC-06), dashboard (EPIC-07).

## Interfaces & contracts

### Strategy profiles (`src/app/analysis/strategy_profile.py`)

Computed (pandas over DB, no LLM except the positioning summary):
```python
class StrategyProfile(BaseModel):
    competitor: str
    primary_themes: list[str]              # top topics by post share
    content_mix: dict[str, float]          # format-group → % (groups in config)
    best_format: str; best_topic: str      # by avg engagement (min 3 posts)
    posting_frequency_per_week: float
    engagement_windows: list[str]          # e.g. ["Tue","Wed","Thu"] by avg score; day-of-week from posted_at
    positioning_summary: str               # 2-3 sentence LLM summary (prompt: analysis/positioning_summary)
```
Persisted to `strategy_profiles` keyed by run.

### Cross-competitor (`src/app/analysis/cross.py`)

```python
class CrossCompetitorInsights(BaseModel):
    common_themes: list[ThemeStat]         # topic, competitors_covering, post_share
    saturated_topics: list[ThemeStat]      # high share + many competitors
    white_spaces: list[WhiteSpace]         # taxonomy topics with low coverage; plus
                                           # high-engagement/low-frequency topics
    opportunity_topics: list[OpportunityTopic]  # engagement above median, coverage below median
    format_opportunities: list[FormatOpportunity]
        # e.g. video = 8% of posts but 2.4× avg engagement → multiplier computed
    keyword_matrix: list[KeywordPerf]      # term, frequency, avg engagement of posts
                                           # containing it, quadrant: high_freq_high_perf etc.
```
Pure computation; thresholds (median splits, min sample sizes) in `app.yaml: cross`.
Stored as `insights.kind = cross_competitor`.

### Top content report (`src/app/analysis/top_content.py`)

Top-20 posts across competitors (by engagement rate when available, else score —
strategy documented in code). For each, LLM analysis via
`prompts/analysis/why_it_worked.{yaml,md}` (tier reasoning, batch of 5):
```python
class WhyItWorked(BaseModel):
    hook: str; structure: str; emotional_trigger: str | None
    data_usage: str | None; visual_format: str; cta_assessment: str
    audience_relevance: str; timing_note: str | None; length_note: str
    storytelling: str | None; summary: str   # one-line "why" for the table
```
Stored as `insights.kind = top_content`.

## Deliverables

- [x] `strategy_profile.py` + `prompts/analysis/positioning_summary.{yaml,md}` + repo +
      tests on fixture data (hand-computed mix/frequency/windows)
- [x] `cross.py` + schemas + tests: seeded fixture where expected white space, opportunity
      topic, and a 2×-multiplier format opportunity are known in advance
- [x] `top_content.py` + `why_it_worked` prompt + tests (ranking strategy incl. missing
      follower data; batch analysis parse)
- [x] Graph wiring: `profiles → cross → top_content` stages
- [x] Keyword matrix quadrant logic + tests (frequency ≠ performance demonstrated)

## Acceptance criteria

1. Profiles reproduce hand-computed values on fixtures (mix percentages sum to 100 ±1,
   frequency correct for the period).
2. Cross insights find the planted white space and format opportunity in the fixture;
   thresholds configurable.
3. Keyword matrix places a planted high-frequency/low-performance keyword and a
   low-frequency/high-performance keyword in the correct quadrants.
4. Top-20 report has 20 rows (or all posts if fewer) each with a WhyItWorked record.
5. `make test` offline; `make demo` includes all EPIC-05 stages.

## Implementation notes

- **Separate graph, not an extension of the EPIC-04 graph.** `map_strategy_run`
  (`src/app/analysis/mapping_graph.py`) compiles its own `profiles → cross → top_content`
  StateGraph and is called after `analyze_run`. This keeps the EPIC-04 analysis graph and
  its tests (which assert `run.stage == "campaigns"`) untouched. `demo.py` now calls both.
- **`content_mix` groups** live in `config/app.yaml: format_groups` (group → list of
  taxonomy formats); `AppConfig` gained `format_groups`, `strategy`, `company` fields.
  Every configured group is always present in the mix (0.0 when empty) so the dashboard
  has a stable key set; percentages sum to 100 ±rounding.
- **`cross` thresholds** all live in `config/app.yaml: cross` (common/saturation/whitespace
  competitor counts, format-opportunity multiplier + max share, keyword min frequency,
  top-content size, why-it-worked batch size). Medians for the opportunity/quadrant splits
  are computed over topics/keywords that clear the minimum-sample floor.
- **Top-content ranking strategy** (documented in `top_content.py`): rank by
  `engagement_rate` only when *every* scored post in the run has one, else by
  `engagement_score`; the chosen key is recorded in `TopContentReport.ranked_by`. Mixing
  the two keys per-post would let large-follower competitors dominate.
- **Persistence:** `StrategyProfileRepo.replace_for_run` writes `strategy_profiles`;
  `InsightRepo.put` writes one `insights` row per (run, kind) for `cross_competitor` and
  `top_content` (payloads are `model_dump(mode="json")`). `InsightRepo` is the shared
  home for every `insights.kind` used by EPIC-05/06/08.
- **Offline:** `register_mapping_fakes` (`src/app/analysis/mapping_fakes.py`) supplies
  deterministic `positioning_summary` and `why_it_worked` responders; wired into `demo.py`
  and the test fixtures.
