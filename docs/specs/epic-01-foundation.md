# EPIC-01 — Foundation

**Objective:** Project scaffold plus the two core services every later epic depends on:
the `ModelRouter` (OpenRouter free → NVIDIA NIM → Groq fallback) and the
`PromptRegistry` (YAML + Markdown prompt pairs). Plus config, DB base, logging, tooling.

## Scope

**In:** repo scaffold, pyproject/Makefile/Docker, settings, models.yaml, DB engine +
base models + repos skeleton, ModelRouter with fallback + structured output + FakeLLM,
PromptRegistry, structlog setup, FastAPI app skeleton with `/api/health`, pytest setup.
**Out:** any pipeline logic, adapters, prompts for real features (one example prompt
only), frontend.

## Interfaces & contracts

### Settings (`src/app/config/settings.py`, pydantic-settings)

Env vars (see `.env.example`): `OPENROUTER_API_KEY`, `NVIDIA_API_KEY`, `GROQ_API_KEY`,
`DATABASE_URL` (default `sqlite:///data/app.db`), `LLM_FAKE_MODE` (default `false`),
`LOG_LEVEL`. YAML app config loaded from `config/app.yaml` (analysis defaults, batch
size, engagement weights) and `config/models.yaml`.

### `config/models.yaml`

```yaml
tiers:
  fast:
    openrouter: ["meta-llama/llama-3.3-70b-instruct:free", "google/gemini-2.0-flash-exp:free"]
    nvidia: ["meta/llama-3.3-70b-instruct"]
    groq: ["llama-3.3-70b-versatile"]
  reasoning:
    openrouter: ["deepseek/deepseek-r1:free", "deepseek/deepseek-chat:free"]
    nvidia: ["deepseek-ai/deepseek-r1"]
    groq: ["deepseek-r1-distill-llama-70b"]
providers:
  openrouter: {base_url: "https://openrouter.ai/api/v1", rpm: 20}
  nvidia:     {base_url: "https://integrate.api.nvidia.com/v1", rpm: 40}
  groq:       {base_url: "https://api.groq.com/openai/v1", rpm: 30}
```

(Model IDs are config, expected to rotate; code must not depend on specific IDs.)

### ModelRouter (`src/app/core/model_router.py`)

```python
class ModelRouter:
    def __init__(self, settings, models_config): ...
    def invoke(self, *, tier: str, system: str, user: str,
               schema: type[BaseModel], temperature: float,
               prompt_name: str, prompt_version: int) -> BaseModel: ...
```

Behavior:
- Builds per-tier chain: first configured OpenRouter model, with fallbacks to NVIDIA
  then Groq (`ChatOpenAI` with per-provider `base_url`/key), using LangChain
  `.with_fallbacks()`.
- Retries 429/5xx with exponential backoff (tenacity), max 3 attempts per provider.
- Structured output: request JSON; parse via `schema.model_validate_json` after
  extracting a JSON block if fenced; on validation error, one repair round-trip
  (re-prompt with the error), then raise `LLMOutputError`.
- `LLM_FAKE_MODE=true` (or missing all keys) → `FakeLLM` returns deterministic payloads
  registered per schema by tests/demo fixtures.
- Logs every call: prompt_name, version, tier, provider used, latency, retry count.

### PromptRegistry (`src/app/core/prompt_registry.py`)

```python
class PromptRegistry:
    def __init__(self, prompts_dir: Path, schema_registry: dict[str, type[BaseModel]]): ...
    def get(self, name: str) -> PromptSpec       # metadata + template
    def render(self, name: str, **variables) -> RenderedPrompt  # system, user, meta
```

- Scans `prompts/**/*.yaml`, validates metadata (required fields per prompt-authoring
  skill), pairs with `.md`, splits on `---USER---`, renders with Jinja2
  (`StrictUndefined`), errors on missing/extra declared variables, resolves
  `output_schema` against the schema registry.

### DB (`src/app/db/`)

- `engine.py` — engine/session factory from `DATABASE_URL`; `init_db()` creates tables.
- `models.py` — all tables from solution-design §6 defined now (later epics fill them):
  competitors, company_profiles, posts, post_intelligence, campaigns, runs,
  strategy_profiles, insights.
- `repos.py` — `CompetitorRepo`, `RunRepo` with basic CRUD; later epics extend.

### API skeleton (`src/app/api/`)

`main.py` creates the app, wires structlog, mounts routers; `GET /api/health` returns
`{"status": "ok", "version": ...}`.

## Deliverables

- [x] `pyproject.toml` (deps: fastapi, uvicorn, langchain, langchain-openai, langgraph,
      deepagents, sqlalchemy, pydantic-settings, pandas, openpyxl, jinja2, structlog,
      tenacity, apscheduler, scikit-learn, pytest, httpx, ruff), `Makefile`
      (install/test/lint/run/demo), `.env.example`, `.gitignore`, `README.md` stub
- [x] `config/app.yaml`, `config/models.yaml`
- [x] `src/app/config/settings.py` + loader tests
- [x] `src/app/core/logging.py` (structlog JSON + console dev renderer)
- [x] `src/app/core/model_router.py` + `FakeLLM` + tests (fallback on 429 simulated,
      repair path, fake mode)
- [x] `src/app/core/prompt_registry.py` + example prompt `prompts/example/echo.{yaml,md}`
      + tests (render, missing variable error, schema resolution)
- [x] `src/app/schemas/__init__.py` with schema registry mechanism + `EchoResult` example
- [x] `src/app/db/{engine,models,repos}.py` + tests (init, CRUD roundtrip on sqlite tmp)
- [x] `src/app/api/main.py` + health test (httpx ASGI client)
- [x] `Dockerfile` (multi-stage: frontend build stage placeholder + python runtime),
      `docker-compose.yml`
- [x] git repo initialized with initial commit

## Acceptance criteria

1. `make install && make test && make lint` pass on a clean checkout with no API keys.
2. `make run` serves `/api/health` → 200.
3. A test proves: OpenRouter provider raising 429 → call succeeds via NVIDIA fallback
   (mocked transports).
4. A test proves: invalid JSON from the model → repair retry → valid parse; twice
   invalid → `LLMOutputError`.
5. `PromptRegistry.render("echo", ...)` returns system/user strings with variables
   substituted; undeclared variable raises.
6. `init_db()` creates all eight tables in a temp SQLite file.

## Test plan

Unit tests per module as above; no network anywhere (mock `httpx`/LangChain transports).

## Implementation notes (2026-08-27)

- Fallback is implemented as explicit iteration over `(provider, model)` attempts with
  per-attempt tenacity retry, rather than LangChain `.with_fallbacks()` — this gives
  per-provider retry policy, skip-on-missing-key, and logging of which provider served
  the call, which `.with_fallbacks()` hides. Behavior matches the contract otherwise.
- `LLMOutputError` (schema failure after repair) deliberately does NOT trigger provider
  fallback, per contract, to avoid burning quota when the prompt itself is at fault.
- `make demo` currently runs a foundation wiring check (registry → router → schema);
  EPIC-02+ replace it with the full pipeline demo.
