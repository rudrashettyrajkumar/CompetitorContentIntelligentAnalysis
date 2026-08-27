---
name: epic-workflow
description: How to implement one epic of the Competitor Intelligence platform from its spec — read order, implementation loop, verification, and close-out. Use whenever implementing or resuming an epic from docs/specs/.
---

# Epic Workflow

Each epic is implemented by a fresh agent session. This skill is the contract for how
that session runs.

## 1. Orient (before writing any code)

Read in this order:
1. `CLAUDE.md` — conventions and hard constraints.
2. `docs/solution-design.md` — architecture; find your epic's row in the layer map.
3. Your epic spec `docs/specs/epic-0N-*.md` — objective, contracts, deliverables,
   acceptance criteria.
4. The **Interfaces & contracts** sections of earlier epics' specs that you depend on,
   then the actual code implementing them (`src/app/core/`, `src/app/schemas/`,
   `src/app/db/`). The code is the truth if spec and code disagree — note the drift.

## 2. Implement

- Work through the spec's Deliverables checklist top to bottom; earlier items are
  dependencies of later ones.
- For each deliverable: write the module → write its tests → run the tests. Do not
  batch all testing to the end.
- New data shapes go in `src/app/schemas/` (Pydantic v2). New queries go in
  `src/app/db/repos.py`. New prompts follow the `prompt-authoring` skill.
- Anything configurable in the spec (weights, periods, batch sizes, taxonomies) goes in
  `config/*.yaml`, not constants in code.

## 3. Verify (all must pass before close-out)

```bash
make lint
make test        # offline: FakeLLM + MockAdapter
make demo        # epics ≥ 02: full pipeline on sample data must complete
```

Then walk the spec's **Acceptance criteria** one by one and confirm each with concrete
evidence (a test name, a command output, an API response).

## 4. Close out

- Check off completed Deliverables items in the spec file (edit the `- [ ]` boxes).
- If you deviated from the spec, add a short **Implementation notes** section at the
  bottom of the spec saying what and why.
- Final report: deliverables done, files touched, pytest summary line, open issues for
  the next epic.

## Rules of engagement

- Scope is the spec. Missing groundwork from an earlier epic → minimal fix + flag it.
- Never break `make test` for previously completed epics.
- No network in tests. No quota spend in the demo path.
