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
make test                   # offline test suite
make demo                   # end-to-end demo (mock data, no quota spent)
make run                    # API on http://localhost:8000
```

## Documentation

- `docs/solution-design.md` — architecture, constraints, data model
- `docs/specs/` — one spec per epic (EPIC-01 … EPIC-08)
- `CLAUDE.md` — conventions for AI-assisted epic implementation

## Status

| Epic | Status |
|---|---|
| 01 Foundation (config, LLM router, prompt registry, DB, API skeleton) | ✅ |
| 02 Input & Data Layer | ⬜ |
| 03 Intelligence Layer | ⬜ |
| 04 Engagement & Campaigns | ⬜ |
| 05 Strategy Mapping & Cross-Competitor | ⬜ |
| 06 AI Strategy Layer | ⬜ |
| 07 API & Dashboard | ⬜ |
| 08 Continuous Loop | ⬜ |

> **Compliance note:** automated scraping of LinkedIn violates LinkedIn's User
> Agreement. The Playwright adapter is disabled by default; the demo path uses
> synthetic/imported data. See `docs/solution-design.md` §7.
