# Solution Design — Competitor & Content Intelligence Platform

**Status:** Approved · **Date:** 2026-08-27 · **Owner:** Raj

## 1. Problem & Objective

Ingest a dynamic list of competitors (Excel), collect their publicly available LinkedIn
activity over a configurable period, and run it through an AI pipeline that answers:

- What are competitors talking about, in which formats, how often?
- Which topics, campaigns, keywords, and CTAs drive the strongest engagement?
- Where are the white spaces and format opportunities?
- How do we convert those patterns into an **original, differentiated** content strategy,
  concrete content opportunities, and a 30-day calendar?

The system is a continuously running product, not a one-off script: recurring collection,
period-over-period comparison, and strategy updates.

## 2. Constraints

| Constraint | Consequence |
|---|---|
| Everything free or open-source | SQLite, self-hosted FastAPI, free LLM tiers, OSS libraries only |
| OpenRouter `:free` models primary; NVIDIA NIM and Groq fallback | `ModelRouter` with a provider fallback chain, retry/backoff, quota awareness |
| LangChain + LangGraph + FastAPI + deepagents | Pipeline is a LangGraph `StateGraph`; deep agents for campaign detection & strategy generation |
| Modular prompting | Every prompt = `.yaml` metadata + `.md` Jinja2 template under `prompts/`, loaded by `PromptRegistry` |
| Built epic-by-epic by fresh Claude agents | `CLAUDE.md`, subagents, skills, and one spec per epic in `docs/specs/` |

## 3. High-Level Architecture

```
                     ┌────────────────────────────────────────────────────────────┐
                     │                        FastAPI (src/app/api)               │
                     │   /competitors  /runs  /results/*  /exports/*  /schedule   │
                     └───────────────┬────────────────────────────┬───────────────┘
                                     │ triggers                    │ serves
                                     ▼                            ▼
┌──────────┐   ┌───────────┐   ┌──────────────────────────┐   ┌──────────────┐
│  Excel   │──►│  Input    │──►│  LangGraph Pipeline       │   │ React SPA    │
│  upload  │   │  Layer    │   │  (src/app/graph)          │   │ (frontend/)  │
└──────────┘   └───────────┘   │                           │   └──────────────┘
                               │ collect ► enrich ► classify│
                               │ ► score ► campaigns ►      │
                               │ profiles ► cross-compare ► │
                               │ top-content ► strategy ►   │
                               │ opportunities ► calendar   │
                               └─────┬──────────────┬───────┘
                                     │              │
                          ┌──────────▼───┐   ┌──────▼─────────┐
                          │ DataSource   │   │ ModelRouter    │
                          │ adapters     │   │ OpenRouter free│
                          │ playwright / │   │ → NVIDIA NIM   │
                          │ apify /      │   │ → Groq         │
                          │ import / mock│   └────────────────┘
                          └──────────────┘
                     SQLite (SQLAlchemy) persists everything; APScheduler re-runs the
                     pipeline on a schedule and diffs against previous periods.
```

### 3.1 Layer map (brief step → module)

| Brief step | Module | Mechanism |
|---|---|---|
| 1 Competitor input | `src/app/input/` | pandas/openpyxl ingest, Pydantic validation, LinkedIn URL validation, dynamic N competitors |
| 2 Company discovery | `src/app/datasources/` | adapter `fetch_company_profile()` |
| 3 Post collection | `src/app/datasources/` | adapter `fetch_posts(period)`; period configurable 7/10/30/60/90 days |
| 4 Engagement intelligence | `src/app/analysis/engagement.py` | weighted score + follower-normalized rate, top-N queries |
| 5 Format intelligence | `src/app/intelligence/format.py` | LLM classification node (17-format taxonomy) |
| 6 Topic & keyword intelligence | `src/app/intelligence/{topics,keywords}.py` | LLM classification + TF-IDF cross-check; frequency-vs-performance matrix |
| 7 Campaign intelligence | `src/app/analysis/campaigns.py` | deep agent: cluster posts into campaigns, name them, capture full campaign record |
| 8 Strategy mapping | `src/app/analysis/strategy_profile.py` | per-competitor profile (themes, mix, cadence, windows) |
| 9 Cross-competitor | `src/app/analysis/cross.py` | common themes, white spaces, saturation, format opportunities |
| 10 Top content report | `src/app/analysis/top_content.py` | Top-20 + LLM "why it worked" breakdown |
| 11 AI strategy | `src/app/strategy/` | deep agent: pillars, content mix, formats |
| 12 Opportunities | `src/app/strategy/opportunities.py` | original content recommendations with hooks/angles/CTAs |
| 13 Calendar | `src/app/strategy/calendar.py` | 30-day calendar generation |
| 14 Continuous loop | `src/app/scheduler/` | APScheduler + period diffing + change reports |

## 4. LLM Strategy

### 4.1 Provider chain

All providers expose OpenAI-compatible APIs, so each is a `ChatOpenAI` instance with a
different `base_url`:

1. **OpenRouter** — `https://openrouter.ai/api/v1`, models with `:free` suffix
   (~20 req/min, 50–1000 req/day depending on account history).
2. **NVIDIA NIM** — `https://integrate.api.nvidia.com/v1` (~40 req/min, developer credits).
3. **Groq** — `https://api.groq.com/openai/v1` (per-model daily caps).

`ModelRouter` builds the chain with LangChain `.with_fallbacks()`, adds exponential
backoff on 429/5xx, and tags every call with the prompt name for logging. Model IDs live
in `config/models.yaml` (free model rosters rotate; never hardcode IDs in Python).

Two logical model tiers, mapped in config:
- `fast` — cheap classification (format, topic, keywords, CTA) e.g. small Llama/Gemini-class free models.
- `reasoning` — campaign clustering, strategy generation e.g. DeepSeek-class free models.

### 4.2 Quota discipline

- **Batching:** classification prompts take up to N posts per call (configurable, default 10).
- **Caching:** classification results persist per post; re-runs only process new posts.
- **FakeLLM:** tests and `make demo` can run with a deterministic fake — zero quota, offline.

### 4.3 Structured output

Every LLM call: `PromptRegistry.render(name, **vars)` → `ModelRouter.invoke(prompt, schema=PydanticModel)`.
Free models are unreliable JSON emitters, so the router uses JSON-mode where supported,
falls back to fenced-JSON extraction + `model_validate_json`, and retries once with a
repair prompt on validation failure.

## 5. Prompt Management

```
prompts/
  intelligence/
    format_classify.yaml     # metadata
    format_classify.md       # Jinja2 template
    topic_classify.{yaml,md}
    keyword_extract.{yaml,md}
  campaigns/campaign_cluster.{yaml,md}
  analysis/why_it_worked.{yaml,md}
  strategy/{pillars,opportunities,calendar}.{yaml,md}
```

YAML metadata schema:

```yaml
name: format_classify
version: 1
description: Classify LinkedIn posts into the 17-format taxonomy
model_tier: fast            # fast | reasoning
temperature: 0.1
output_schema: FormatClassification   # Pydantic model name in src/app/schemas
batch: true                 # accepts multiple posts per call
variables: [posts, taxonomy]
```

The `.md` file is the Jinja2 template body (system + user sections split by a
`---USER---` delimiter). `PromptRegistry` validates that all `variables` are supplied at
render time and that `output_schema` resolves to a registered Pydantic model.

## 6. Data Model (SQLAlchemy, SQLite → Postgres-ready)

- `competitors` — name, linkedin_url, industry, market, priority, website, status
- `company_profiles` — competitor_id, description, followers, geo, services (JSON), positioning, fetched_at
- `posts` — competitor_id, run_id, posted_at, url (unique), content, raw_format, reactions, comments, reposts, source_adapter
- `post_intelligence` — post_id, format, topic, sub_topic, cta, hashtags (JSON), keywords (JSON), engagement_score, engagement_rate, prompt_versions (JSON)
- `campaigns` — competitor_id, run_id, name, theme, objective, post_ids (JSON), start/end, formats, keywords, hashtags, cta, audience, total_engagement, top_post_id
- `runs` — id, started_at, period_days, adapter, status, stage, error
- `strategy_profiles` — competitor_id, run_id, themes, content_mix, best_format, best_topic, cadence, engagement_windows (all JSON)
- `insights` — run_id, kind (cross_competitor | top_content | strategy | opportunities | calendar | period_diff), payload (JSON)

Everything downstream of collection is derived data keyed by `run_id`, so periods can be
compared and re-analysis never mutates raw posts.

## 7. Data Collection & Compliance

`DataSource` ABC (`src/app/datasources/base.py`):

```python
class DataSource(ABC):
    def fetch_company_profile(self, url: str) -> CompanyProfile: ...
    def fetch_posts(self, url: str, since: date) -> list[RawPost]: ...
```

Adapters:
- **MockAdapter** — deterministic synthetic dataset (seeded), realistic distributions across formats/topics/engagement; powers demos and tests.
- **ImportAdapter** — CSV/JSON files matching a documented schema (manual export, third-party exports).
- **ApifyAdapter** — calls Apify LinkedIn actors via their API (free $5/month credit).
- **PlaywrightAdapter** — open-source browser automation of public pages. **Disabled by default.**

> **Compliance note:** hiQ v. LinkedIn (9th Cir.) held that scraping public data does not
> violate the CFAA, but automated collection still violates LinkedIn's User Agreement.
> The Playwright adapter therefore ships behind an explicit config flag with this warning,
> and the default demo path uses Mock/Import. Choice and risk sit with the operator.

## 8. Deep Agents (deepagents library)

Used in exactly two places, where iterative planning beats a single prompt:

1. **Campaign detection** (`EPIC-04`): agent receives the classified post set as virtual
   files, iteratively clusters by theme/keywords/time-proximity, names campaigns,
   gathers per-campaign evidence, and emits validated `Campaign` records.
2. **Strategy generation** (`EPIC-06`): agent reads the structured intelligence
   (profiles, cross-competitor insights, top content) as files and produces pillars →
   content mix → opportunities → 30-day calendar, with an **originality guard** subagent
   that rejects any output too similar to a competitor post (n-gram overlap check + LLM
   similarity judgment).

Everything else is plain LangGraph nodes — cheaper, deterministic, easier to test.

## 9. API Surface (FastAPI)

- `POST /api/competitors/upload` — Excel upload → validation report + stored competitors
- `GET  /api/competitors` — list with status
- `POST /api/runs` — start pipeline (body: period_days, adapter, competitor filter); runs in background
- `GET  /api/runs/{id}` — status incl. current graph stage
- `GET  /api/results/{run_id}/…` — `summary | posts | formats | topics | keywords | campaigns | profiles | cross | top-content | strategy | opportunities | calendar`
- `GET  /api/exports/{run_id}.xlsx|.json` — full intelligence workbook / bundle
- `POST /api/schedule` / `GET /api/schedule` — recurring loop config
- `GET  /api/health`

React SPA (Vite build) served at `/` via `StaticFiles`; dashboards: KPI header,
engagement trends, format/topic performance, campaign table, white-space matrix,
opportunities, calendar view.

## 10. Continuous Intelligence Loop (Step 14)

APScheduler job (cron, default weekly) → new run → after completion a **diff stage**
compares against the previous run: new posts, new campaigns, emerging keywords
(frequency delta), topic performance shifts, profile changes → stored as
`insights.kind = period_diff` and surfaced on the dashboard; strategy regeneration is
triggered when drift exceeds configurable thresholds.

## 11. Epics

See `docs/specs/epic-0N-*.md`. Order: 01 Foundation → 02 Input+Data → 03 Intelligence →
04 Engagement+Campaigns → 05 Strategy mapping+Cross → 06 AI Strategy → 07 API+Dashboard
→ 08 Continuous loop. Each epic is implemented by a fresh Claude agent following
`CLAUDE.md` + the `epic-workflow` skill, against its spec's acceptance criteria.

## 12. Testing & Verification

- `make test` — pytest, fully offline (FakeLLM + MockAdapter), covers every layer.
- `make demo` — end-to-end: sample Excel (5 competitors) → mock collection → full
  pipeline → exports + dashboard at `http://localhost:8000`.
- Provider smoke test (needs keys in `.env`): one real call per provider + simulated 429
  on OpenRouter to prove fallback to NIM → Groq.
- Each epic's spec has its own acceptance criteria; `spec-guardian` subagent verifies
  implementation against spec before an epic is closed.
