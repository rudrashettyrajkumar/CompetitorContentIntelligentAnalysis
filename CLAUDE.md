# Competitor & Content Intelligence Platform

End-to-end LinkedIn competitor intelligence: Excel input → data collection → AI
classification → engagement/campaign analysis → original content strategy + 30-day
calendar → React dashboard → recurring intelligence loop.

**Read first:** `docs/solution-design.md` (architecture, constraints, data model).
**Work is organized in epics:** one spec per epic in `docs/specs/`. If you are
implementing an epic, follow the `epic-workflow` skill and your epic's spec exactly.

## Hard constraints (never violate)

- **Free/open-source only.** No paid services, no proprietary SaaS dependencies.
- **LLM chain:** OpenRouter `:free` models primary → NVIDIA NIM → Groq fallback. All
  LLM calls go through `src/app/core/model_router.py`. Never instantiate a chat model
  directly in feature code. Model IDs live in `config/models.yaml`, never in Python.
- **All prompts** are `prompts/<section>/<name>.yaml` + `.md` pairs loaded via
  `PromptRegistry` (`src/app/core/prompt_registry.py`). Never inline prompt strings in
  Python. Follow the `prompt-authoring` skill.
- **Frameworks:** LangGraph for the pipeline, deepagents only for campaign detection and
  strategy generation, FastAPI for the API, React (Vite) in `frontend/` for the dashboard.
- **Structured output:** every LLM response validates against a Pydantic model in
  `src/app/schemas/`.

## Stack & layout

Python 3.11+, SQLAlchemy 2.0 + SQLite (Postgres-ready), pydantic-settings, structlog,
APScheduler, pytest. Source in `src/app/` (`config/ core/ input/ datasources/ schemas/
intelligence/ analysis/ strategy/ graph/ api/ db/ scheduler/`), prompts in `prompts/`,
tests in `tests/` mirroring `src/app/`.

## Commands

```bash
make install    # create venv + install deps (uv preferred, pip fallback)
make test       # pytest — fully offline (FakeLLM + MockAdapter); must pass before any epic closes
make lint       # ruff check + ruff format --check
make run        # uvicorn dev server on :8000
make demo       # end-to-end pipeline on sample Excel + mock data
```

## Conventions

- Type hints everywhere; Pydantic v2 models for all inter-layer data contracts.
- Repositories in `src/app/db/repos.py` own all queries — no raw SQLAlchemy in feature code.
- Derived data is keyed by `run_id`; never mutate raw `posts` rows during analysis.
- LLM economy: batch posts per classification call (default 10), cache results in DB,
  and always support the FakeLLM path so tests/demo never spend quota.
- structlog with key-value context (`run_id`, `competitor`, `prompt_name`); no `print`.
- Tests never hit the network. Adapters and providers get fakes/fixtures.
- LinkedIn compliance: the Playwright adapter stays disabled by default; do not remove
  the warning or flip the default (see solution-design §7).

## Definition of done (every epic)

1. All acceptance criteria in the epic spec met.
2. `make test` and `make lint` pass; new code has tests.
3. `make demo` still runs end-to-end (for epics ≥ 02).
4. Prompts added as YAML+md pairs with registered schemas.
5. Spec's "Deliverables" checklist updated (check items off in the spec file).
