# EPIC-06 — AI Strategy Layer (brief steps 11–13)

**Objective:** A deepagents-powered strategy generator that converts the structured
intelligence into an original content strategy: pillars, content mix, formats, concrete
content opportunities, and a 30-day calendar — with an originality guard.

## Scope

**In:** strategy deep agent, opportunity generation, calendar generation, originality
guard, company-context config, persistence + export-ready schemas.
**Out:** API/dashboard surfaces (EPIC-07), scheduling (EPIC-08).

## Interfaces & contracts

### Company context (`config/company.yaml`)

Our company's profile the strategy is generated FOR: name, industry, services, target
audience, differentiators, tone. Used by all strategy prompts; sample values shipped.

### Strategy deep agent (`src/app/strategy/generator.py`)

deepagents agent, `reasoning` tier. Input virtual files: strategy profiles, cross
insights, top-content report, campaign records, keyword matrix, company context.
Produces in three steps (agent-internal plan, each output validated):

```python
class ContentStrategy(BaseModel):
    pillars: list[Pillar]                  # 4-6: name, description, rationale (cites
                                           # which competitor signal/white space)
    content_mix: dict[str, float]          # category → %; sums to 100
    recommended_formats: list[FormatRec]   # format, share, rationale
    posting_cadence: str; engagement_windows: list[str]

class ContentOpportunity(BaseModel):       # 8-12 of these
    topic: str; pillar: str
    competitor_signal: Literal["high","medium","low"]
    competition_level: Literal["high","medium","low"]
    engagement_potential: Literal["high","medium","low"]
    recommended_format: str; target_audience: str
    hook: str; angle: str; key_message: str
    structure: list[str]                   # outline sections
    cta: str; keywords: list[str]; hashtags: list[str]

class CalendarEntry(BaseModel):            # 30 days, respecting cadence (not 30 posts/30 days)
    day: int; weekday: str; pillar: str; topic: str
    format: str; objective: str; cta: str; opportunity_ref: int | None
class ContentCalendar(BaseModel):
    entries: list[CalendarEntry]; cadence_note: str
```

Prompts: `prompts/strategy/{pillars,opportunities,calendar}.{yaml,md}`.

### Originality guard (`src/app/strategy/originality.py`)

Every generated hook/angle/key_message checked against all competitor post texts:
1. Deterministic: normalized 6-gram overlap ratio; > threshold (config, default 0.30)
   → reject.
2. LLM judge (`prompts/strategy/originality_check.{yaml,md}`, fast tier, batch): "is
   this a rewrite of any of these excerpts?" → reject on yes.
Rejected items are regenerated once with the rejection reason fed back; still failing →
dropped and logged. Guard results stored with the strategy.

Deterministic derivation rules (Python, not LLM): competitor_signal from topic post
volume, competition_level from coverage, engagement_potential from cross-insight
quadrants — the LLM proposes, the code stamps these three fields from data so they are
auditable.

## Deliverables

- [x] `config/company.yaml` + settings plumbing (`get_company_context` / `CompanyContext`)
- [x] `schemas/strategy.py` + registry entries
- [x] `generator.py` deep agent (`DeepStrategyAgent`) + offline scripted stub
      (`FakeStrategyAgent`)
- [x] 5 strategy prompt packs (pillars, opportunities, calendar, originality_check,
      regenerate_field) + render/parse tests
- [x] `originality.py` + tests: a planted near-copy of a competitor post is rejected by
      the n-gram check; LLM-layer catch; regeneration path covered
- [x] Signal-stamping derivation rules + tests (incl. "agent lies, data wins")
- [x] Graph wiring: `strategy → opportunities → calendar` stages; persistence as
      `insights.kind = strategy | opportunities | calendar`
- [x] Calendar validation: 30 consecutive days, entries only on cadence days, every
      entry maps to a pillar, mix within ±10% of the recommended mix

## Acceptance criteria

1. Full pipeline on mock data yields: 4–6 pillars each citing a competitor signal,
   content mix summing to 100, 8–12 opportunities with all fields populated, and a
   valid 30-day calendar (per calendar validation above).
2. Originality: near-duplicate content is rejected (test with planted copy); guard
   verdicts persisted.
3. Signal fields (competitor_signal / competition_level / engagement_potential) are
   reproducibly derived from data, not free LLM output (test asserts derivation).
4. `make test` offline; `make demo` produces the complete strategy bundle.

## Implementation notes

- **Own LangGraph, run after the EPIC-05 mapping stage.** `run_strategy_stage`
  (`src/app/strategy/graph.py`) compiles a `strategy → opportunities → calendar`
  StateGraph; each node sets `run.stage`, runs a step from `strategy/generator.py`, and
  writes one `insights` row (`strategy`, `opportunities`, `calendar`). `generate_strategy`
  in `generator.py` composes the same steps without persistence for direct callers/tests.
- **Agents.** `FakeStrategyAgent` derives a fully valid, schema-conformant bundle straight
  from `StrategyInputs` (offline, zero quota) and is what tests + demo use.
  `DeepStrategyAgent` runs one deepagents pass per step (`reasoning` tier) over the
  EPIC-05 intelligence as virtual files, falling back to `router.invoke` on error — same
  pattern as `DeepCampaignAgent`.
- **`StrategyInputs`** (`strategy/inputs.py`) is assembled once per run: company context,
  EPIC-05 profiles (from `strategy_profiles`), cross + top-content (re-hydrated from
  `insights`), campaign records, every raw post body (for the guard), and `topic_stats`
  (per-topic volume / coverage / engagement + cross quadrant flags).
- **Signal stamping** (`strategy/derivation.py`): `competitor_signal` ← topic post-share,
  `competition_level` ← competitor coverage count, `engagement_potential` ← quadrant
  flags / above-median engagement. The agent fills these fields but the code overwrites
  them from `topic_stats` so they are reproducible. Cut-offs in `config: strategy`.
- **Originality guard** (`strategy/originality.py`): layer 1 is a normalized n-gram
  overlap ratio (n + threshold in `config: strategy`; short texts fall back to k<n grams);
  layer 2 is the batched `originality_check` LLM judge. A rejected `hook`/`angle`/
  `key_message` is regenerated once via a `regenerate` callback (the agent's
  `regenerate_field`); if it still fails, the whole opportunity is dropped. Every
  decision is an `OriginalityCheck`, persisted under the `opportunities` insight.
- **Calendar validation** (`strategy/calendar_check.py`) is deterministic and also gates
  the fake agent's own output — `FakeStrategyAgent.calendar` builds a Mon-anchored 30-day
  grid on the cadence weekdays with pillars allocated by largest-remainder against
  `content_mix`, so it passes its own validator.
- Added a 5th prompt pack, `regenerate_field` (schema `RegeneratedField`), for the deep
  agent's single-field regeneration — the 4 in the spec plus this.
- `AppConfig` already carried `strategy` (added in EPIC-05); `company` field is unused so
  far (company profile is its own `config/company.yaml`).
