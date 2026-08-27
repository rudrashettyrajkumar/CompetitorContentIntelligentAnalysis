---
name: prompt-authoring
description: Conventions for creating LLM prompts in this repo — YAML metadata + Markdown Jinja2 template pairs under prompts/, registered output schemas, batching, and versioning. Use whenever adding or editing a prompt.
---

# Prompt Authoring

Every prompt is a **pair of files** in `prompts/<section>/`:

```
prompts/intelligence/format_classify.yaml   # metadata
prompts/intelligence/format_classify.md     # Jinja2 template
```

Python never contains prompt text. All calls go through
`PromptRegistry.render(name, **variables)` → `ModelRouter.invoke(...)`.

## YAML metadata (required fields)

```yaml
name: format_classify        # must equal the filename stem and be globally unique
version: 1                   # bump on any meaningful wording/schema change
description: One line on what this prompt does
model_tier: fast             # fast (classification) | reasoning (clustering/strategy)
temperature: 0.1             # classification ≤ 0.2; generation 0.6–0.8
output_schema: FormatClassification   # Pydantic class name registered in src/app/schemas
batch: true                  # true if the template accepts a list of items per call
variables: [posts, taxonomy] # every Jinja2 variable the template uses — validated at render
```

## Markdown template

System and user sections split by a literal `---USER---` line:

```markdown
You are a content intelligence analyst. Classify LinkedIn posts strictly into the
provided taxonomy. Respond with JSON only, matching the schema exactly.

---USER---
Taxonomy: {{ taxonomy | join(", ") }}

Posts:
{% for post in posts %}
[{{ loop.index }}] {{ post.content | truncate(600) }}
{% endfor %}
```

## Rules

- **Schema-first:** define/choose the Pydantic output model before writing the prompt.
  Instruct "JSON only, matching the schema"; the router handles JSON-mode/extraction/repair.
- **Batching:** classification prompts must accept a list (`batch: true`) — free-tier
  request quotas are the scarce resource, not tokens. Index items `[1]…[n]` and have the
  schema return results keyed by index.
- **Free-model friendly:** short system sections, explicit enumerated taxonomies, one
  task per prompt, an inline example for anything non-obvious. These run on small free
  models — do not write prompts that need frontier-model inference.
- **Originality guard (strategy prompts):** generation prompts must instruct the model
  to produce original angles and must NOT include competitor post text verbatim beyond
  brief evidence snippets; recommendations may reference patterns, never copy content.
- **Versioning:** bump `version` when wording changes materially; `post_intelligence`
  rows record the prompt versions used, so cached results invalidate automatically when
  the version changes.
- **Testing:** every prompt gets a render test (template renders with sample variables;
  all declared variables used) and a parse test (FakeLLM returns a valid + an invalid
  payload; router repair path covered once centrally).
