"""LangGraph classification subgraph (brief steps 5-6).

``load_unclassified -> format -> topic -> cta -> keywords -> tfidf_crosscheck -> persist``

Nodes run sequentially, each batched. Only posts missing a ``post_intelligence`` row for
the current prompt versions are loaded, so a re-run classifies nothing and a prompt
version bump reprocesses. Fully offline under FakeLLM.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, TypedDict

from langgraph.graph import END, START, StateGraph
from sqlalchemy.orm import Session

from app.config.settings import AppConfig, Taxonomies, get_app_config, get_taxonomies
from app.core.logging import get_logger
from app.core.model_router import ModelRouter
from app.core.prompt_registry import PromptRegistry
from app.db.repos import PostIntelligenceRepo, RunRepo
from app.intelligence.batching import PostItem
from app.intelligence.cta import classify_ctas
from app.intelligence.format import classify_formats
from app.intelligence.keywords import classify_keywords, tfidf_crosscheck
from app.intelligence.topics import classify_topics
from app.schemas.collection import parse_hashtags
from app.schemas.intelligence import KeywordTag, PostClassification

log = get_logger(__name__)

PROMPT_NAMES = ("format_classify", "topic_classify", "cta_extract", "keyword_extract")


def current_prompt_versions(registry: PromptRegistry) -> dict[str, int]:
    return {name: registry.get(name).meta.version for name in PROMPT_NAMES}


@dataclass
class ClassifyDeps:
    session: Session
    router: ModelRouter
    registry: PromptRegistry
    taxonomies: Taxonomies
    run_id: int
    batch_size: int
    prompt_versions: dict[str, int]


@dataclass
class ClassifyResult:
    run_id: int
    posts_total: int
    posts_to_classify: int
    posts_classified: int
    cache_hits: int
    batches_per_task: int
    errors: dict[int, str] = field(default_factory=dict)


class ClassifyState(TypedDict, total=False):
    items: list[PostItem]
    formats: dict[int, str]
    topics: dict[int, tuple[str, str | None]]
    ctas: dict[int, tuple[str, str | None]]
    keywords: dict[int, list[KeywordTag]]
    err_format: dict[int, str]
    err_topic: dict[int, str]
    err_cta: dict[int, str]
    err_keyword: dict[int, str]
    classifications: list[PostClassification]


def build_classify_graph(deps: ClassifyDeps) -> Any:
    def load_unclassified(state: ClassifyState) -> ClassifyState:
        repo = PostIntelligenceRepo(deps.session)
        posts = repo.unclassified(deps.run_id, deps.prompt_versions)
        items = [
            PostItem(
                post_id=post.id,
                index=i,
                content=post.content or "",
                media_type=post.raw_format or "unknown",
                hashtags=list(post.hashtags or []),
            )
            for i, post in enumerate(posts)
        ]
        log.info("classify_load", run_id=deps.run_id, unclassified=len(items))
        return {"items": items}

    def format_node(state: ClassifyState) -> ClassifyState:
        results, errors = classify_formats(
            state["items"],
            router=deps.router,
            registry=deps.registry,
            taxonomies=deps.taxonomies,
            batch_size=deps.batch_size,
        )
        return {"formats": results, "err_format": errors}

    def topic_node(state: ClassifyState) -> ClassifyState:
        results, errors = classify_topics(
            state["items"],
            router=deps.router,
            registry=deps.registry,
            taxonomies=deps.taxonomies,
            batch_size=deps.batch_size,
        )
        return {"topics": results, "err_topic": errors}

    def cta_node(state: ClassifyState) -> ClassifyState:
        results, errors = classify_ctas(
            state["items"],
            router=deps.router,
            registry=deps.registry,
            taxonomies=deps.taxonomies,
            batch_size=deps.batch_size,
        )
        return {"ctas": results, "err_cta": errors}

    def keyword_node(state: ClassifyState) -> ClassifyState:
        results, errors = classify_keywords(
            state["items"],
            router=deps.router,
            registry=deps.registry,
            taxonomies=deps.taxonomies,
            batch_size=deps.batch_size,
        )
        return {"keywords": results, "err_keyword": errors}

    def tfidf_node(state: ClassifyState) -> ClassifyState:
        merged = tfidf_crosscheck(state["items"], state.get("keywords", {}))
        return {"keywords": merged}

    def persist_node(state: ClassifyState) -> ClassifyState:
        repo = PostIntelligenceRepo(deps.session)
        failed: set[int] = set()
        for key in ("err_format", "err_topic", "err_cta", "err_keyword"):
            failed.update(state.get(key, {}))

        classifications: list[PostClassification] = []
        for item in state["items"]:
            if item.index in failed:
                continue
            fmt = state.get("formats", {}).get(item.index)
            topic = state.get("topics", {}).get(item.index)
            cta = state.get("ctas", {}).get(item.index)
            if fmt is None or topic is None or cta is None:
                continue
            classification = PostClassification(
                index=item.index,
                format=fmt,
                topic=topic[0],
                sub_topic=topic[1],
                cta=cta[0],
                cta_text=cta[1],
                keywords=state.get("keywords", {}).get(item.index, []),
            )
            hashtags = item.hashtags or parse_hashtags(item.content)
            repo.upsert(
                item.post_id,
                classification,
                hashtags=hashtags,
                prompt_versions=deps.prompt_versions,
            )
            classifications.append(classification)
        deps.session.commit()
        log.info(
            "classify_persist",
            run_id=deps.run_id,
            classified=len(classifications),
            failed=len(failed),
        )
        return {"classifications": classifications}

    graph = StateGraph(ClassifyState)
    graph.add_node("load_unclassified", load_unclassified)
    graph.add_node("format", format_node)
    graph.add_node("topic", topic_node)
    graph.add_node("cta", cta_node)
    graph.add_node("keywords", keyword_node)
    graph.add_node("tfidf_crosscheck", tfidf_node)
    graph.add_node("persist", persist_node)

    graph.add_edge(START, "load_unclassified")
    graph.add_edge("load_unclassified", "format")
    graph.add_edge("format", "topic")
    graph.add_edge("topic", "cta")
    graph.add_edge("cta", "keywords")
    graph.add_edge("keywords", "tfidf_crosscheck")
    graph.add_edge("tfidf_crosscheck", "persist")
    graph.add_edge("persist", END)
    return graph.compile()


def classify_posts_for_run(
    session: Session,
    *,
    run_id: int,
    router: ModelRouter,
    registry: PromptRegistry,
    taxonomies: Taxonomies | None = None,
    app_config: AppConfig | None = None,
    now: datetime | None = None,  # noqa: ARG001 — reserved for parity with collect stage
) -> ClassifyResult:
    """Run the classification subgraph for a collected run and persist ``post_intelligence``."""
    app_config = app_config or get_app_config()
    taxonomies = taxonomies or get_taxonomies()
    batch_size = int(app_config.llm.get("batch_size", 10))
    prompt_versions = current_prompt_versions(registry)

    deps = ClassifyDeps(
        session=session,
        router=router,
        registry=registry,
        taxonomies=taxonomies,
        run_id=run_id,
        batch_size=batch_size,
        prompt_versions=prompt_versions,
    )

    RunRepo(session).set_stage(run_id, "classify")

    pi_repo = PostIntelligenceRepo(session)
    posts_total = _run_post_count(session, run_id)
    to_classify = len(pi_repo.unclassified(run_id, prompt_versions))

    final: ClassifyState = build_classify_graph(deps).invoke({})

    errors: dict[int, str] = {}
    for key in ("err_format", "err_topic", "err_cta", "err_keyword"):
        errors.update(final.get(key, {}))

    return ClassifyResult(
        run_id=run_id,
        posts_total=posts_total,
        posts_to_classify=to_classify,
        posts_classified=len(final.get("classifications", [])),
        cache_hits=posts_total - to_classify,
        batches_per_task=math.ceil(to_classify / batch_size) if to_classify else 0,
        errors=errors,
    )


def _run_post_count(session: Session, run_id: int) -> int:
    from app.db.repos import PostRepo

    return PostRepo(session).count_for_run(run_id)
