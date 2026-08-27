"""Keyword intelligence node (brief step 6): categorized keyword extraction plus a
TF-IDF cross-check that recovers high-signal terms the LLM missed.

``tfidf_crosscheck`` fits scikit-learn TF-IDF over the whole run corpus; the top-N terms
per post that the LLM did not already surface are merged in as ``category: frequent`` /
``source: tfidf``. This is the raw frequency groundwork — the frequency-vs-performance
join happens in EPIC-04/05.
"""

from __future__ import annotations

from collections.abc import Sequence

from sklearn.feature_extraction.text import TfidfVectorizer

from app.config.settings import Taxonomies
from app.core.model_router import ModelRouter
from app.core.prompt_registry import PromptRegistry
from app.intelligence._llm import invoke_prompt, posts_payload
from app.intelligence.batching import PostItem, run_in_batches
from app.schemas.intelligence import KeywordTag

PROMPT = "keyword_extract"

_TOKEN_PATTERN = r"(?u)\b[a-zA-Z][a-zA-Z0-9+/#-]{2,}\b"


def classify_keywords(
    items: Sequence[PostItem],
    *,
    router: ModelRouter,
    registry: PromptRegistry,
    taxonomies: Taxonomies,
    batch_size: int,
) -> tuple[dict[int, list[KeywordTag]], dict[int, str]]:
    """Return ``({index: [KeywordTag]}, {index: error})`` from the LLM (pre TF-IDF)."""

    def call(batch: list[PostItem]) -> dict[int, list[KeywordTag]]:
        result = invoke_prompt(
            registry,
            router,
            PROMPT,
            posts=posts_payload(batch),
            categories=taxonomies.keyword_categories,
        )
        return {r.index: list(r.keywords) for r in result.results}

    return run_in_batches(items, batch_size=batch_size, call=call, task="keyword")


def tfidf_top_terms(corpus: Sequence[str], *, top_n: int = 5) -> list[list[str]]:
    """Top-N TF-IDF terms (uni/bi-gram) per document. Empty lists when the corpus is
    too small or has no usable vocabulary."""
    docs = list(corpus)
    if sum(1 for d in docs if d and d.strip()) < 2:
        return [[] for _ in docs]
    vectorizer = TfidfVectorizer(
        stop_words="english",
        ngram_range=(1, 2),
        max_features=2000,
        token_pattern=_TOKEN_PATTERN,
    )
    try:
        matrix = vectorizer.fit_transform(docs)
    except ValueError:  # empty vocabulary (all stop-words / punctuation)
        return [[] for _ in docs]
    vocab = vectorizer.get_feature_names_out()
    out: list[list[str]] = []
    for row in matrix:
        weights = row.toarray().ravel()
        ranked = weights.argsort()[::-1][:top_n]
        out.append([str(vocab[i]) for i in ranked if weights[i] > 0.0])
    return out


def merge_tfidf_keywords(
    existing: Sequence[KeywordTag], tfidf_terms: Sequence[str]
) -> list[KeywordTag]:
    """Append TF-IDF terms the LLM did not already surface for this post."""
    merged = list(existing)
    have = {tag.term.lower() for tag in merged}
    for term in tfidf_terms:
        norm = term.strip().lower()
        if norm and norm not in have:
            merged.append(KeywordTag(term=norm, category="frequent", source="tfidf"))
            have.add(norm)
    return merged


def tfidf_crosscheck(
    items: Sequence[PostItem],
    llm_keywords: dict[int, list[KeywordTag]],
    *,
    top_n: int = 5,
) -> dict[int, list[KeywordTag]]:
    """Merge per-post TF-IDF terms into the LLM keyword sets across the run corpus."""
    ordered = list(items)
    per_doc_terms = tfidf_top_terms([it.content for it in ordered], top_n=top_n)
    merged: dict[int, list[KeywordTag]] = {}
    for item, terms in zip(ordered, per_doc_terms, strict=True):
        merged[item.index] = merge_tfidf_keywords(llm_keywords.get(item.index, []), terms)
    return merged
