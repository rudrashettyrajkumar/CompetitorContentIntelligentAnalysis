# EPIC-03 — Intelligence Layer (brief steps 5–6)

**Objective:** LangGraph classification stage that enriches every collected post with
format, topic/sub-topic, CTA, keywords, and hashtags — batched, cached, and validated.

## Scope

**In:** classification subgraph + nodes, prompt packs, taxonomies in config, TF-IDF
keyword cross-check, persistence to `post_intelligence`, keyword frequency-vs-
performance groundwork (raw counts; the performance join happens in EPIC-04/05).
**Out:** engagement scoring, campaign clustering, cross-competitor analysis.

## Interfaces & contracts

### Taxonomies (`config/taxonomies.yaml`)

- `formats`: the 17-item list from the brief (static_image, carousel, video, text_only,
  poll, blog_article, case_study, whitepaper_report, customer_story,
  thought_leadership, product_promotion, event_webinar, employer_branding, hiring,
  industry_news, research_data, ai_related).
- `topics`: brief's list (ai, digital_transformation, cloud, cybersecurity,
  data_analytics, digital_marketing, automation, industry_4_0, customer_experience)
  + `other` escape hatch; sub-topic is free-text.
- `cta_types`: follow, comment, share, register, download, learn_more, contact, demo,
  none, other.
- `keyword_categories`: frequent, industry_term, problem_solution, buyer_intent,
  emerging, long_tail.

### Schemas (`src/app/schemas/intelligence.py`)

```python
class PostClassification(BaseModel):
    index: int                       # position in the batch
    format: str                      # from formats taxonomy
    topic: str; sub_topic: str | None
    cta: str; cta_text: str | None
    keywords: list[KeywordTag]       # term + category
class BatchClassification(BaseModel):
    results: list[PostClassification]
```

### Prompts (`prompts/intelligence/`)

- `format_classify.{yaml,md}` — tier fast, batch, uses media_type as a hint but decides
  intent-format (e.g. a carousel that is a case study → case_study).
- `topic_classify.{yaml,md}` — tier fast, batch, topic + sub_topic.
- `cta_extract.{yaml,md}` — tier fast, batch.
- `keyword_extract.{yaml,md}` — tier fast, batch, categorized keywords.
  (Combining into one multi-task prompt is NOT allowed — one task per prompt per the
  prompt-authoring skill; batching is across posts, not tasks.)

### Classification subgraph (`src/app/intelligence/graph.py`)

LangGraph subgraph `classify_posts`:
`load_unclassified → batch → [format, topic, cta, keywords] (sequential nodes, each
batched) → tfidf_crosscheck → persist`.

- **Caching:** only posts lacking a `post_intelligence` row for current prompt versions
  are processed; version bump invalidates.
- **tfidf_crosscheck** (`keywords.py`): scikit-learn TF-IDF over the run's corpus;
  top-N terms per post merged into keywords as category `frequent` if the LLM missed
  them (marked `source: tfidf`).
- Hashtags come from `RawPost.hashtags` (regex parse), not the LLM.
- Batch size from `app.yaml: llm.batch_size` (default 10); a batch failure falls back to
  per-post calls once before recording per-post errors.

## Deliverables

- [ ] `config/taxonomies.yaml`
- [ ] `src/app/schemas/intelligence.py` + registry entries
- [ ] 4 prompt packs with render + parse tests
- [ ] `src/app/intelligence/{format,topics,cta,keywords}.py` node functions
- [ ] `src/app/intelligence/graph.py` subgraph + `PostIntelligenceRepo`
- [ ] FakeLLM fixtures generating plausible classifications for mock content
- [ ] Tests: caching (second run classifies 0), version-bump invalidation, batch
      fallback path, tfidf merge, unknown-taxonomy value rejected then repaired

## Acceptance criteria

1. Running classification on a mock-collected run enriches every post; taxonomy fields
   only contain configured values.
2. Re-running classifies nothing new (cache hit); bumping a prompt version reprocesses.
3. Batch of 10 posts = 1 LLM call per task type (asserted via FakeLLM call counter).
4. TF-IDF terms missing from LLM output appear with `source: tfidf`.
5. `make test` offline; `make demo` now includes classification.
