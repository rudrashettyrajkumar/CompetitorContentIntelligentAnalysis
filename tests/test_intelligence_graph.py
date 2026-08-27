"""End-to-end coverage for the LangGraph classification subgraph (EPIC-03)."""

from datetime import datetime

import pytest

from app.config.settings import get_taxonomies
from app.core.model_router import ModelRouter
from app.db.repos import CompetitorRepo, PostIntelligenceRepo, PostRepo, RunRepo
from app.intelligence import graph as graph_mod
from app.intelligence.fakes import register_classification_fakes
from app.intelligence.graph import classify_posts_for_run
from app.schemas.collection import RawPost

_CONTENT = [
    ("video", "Watch our webinar on cloud migration and automation for platform teams."),
    ("image", "Behind the scenes of our company culture and hiring week."),
    ("text", "A quick thought on cybersecurity, zero trust and threat detection."),
    ("article", "New on our blog: data analytics dashboards that drive retention."),
    ("document", "Download our guide to digital marketing demand gen campaigns."),
    ("carousel", "Swipe through a customer success story about cloud cost control."),
]


@pytest.fixture
def classify_router(settings, models_config, fake_llm):
    register_classification_fakes(fake_llm)
    return ModelRouter(settings, models_config, fake_llm=fake_llm, backoff_base=0)


def _seed_run(session, n: int):
    comp = CompetitorRepo(session).upsert(
        name="Acme", linkedin_url="https://www.linkedin.com/company/acme"
    )
    run = RunRepo(session).create(period_days=30, adapter="mock")
    posts = []
    for i in range(n):
        media, text = _CONTENT[i % len(_CONTENT)]
        posts.append(
            RawPost(
                url=f"https://www.linkedin.com/feed/update/{i}",
                posted_at=datetime(2026, 1, 1, 9, 0),
                content=f"{text} (#{i})",
                media_type=media,
            )
        )
    PostRepo(session).insert_new(
        run_id=run.id, competitor_id=comp.id, posts=posts, source_adapter="mock"
    )
    session.commit()
    return run.id


def test_every_post_enriched_with_configured_values(db_session, classify_router, prompt_registry):
    run_id = _seed_run(db_session, 6)
    result = classify_posts_for_run(
        db_session, run_id=run_id, router=classify_router, registry=prompt_registry
    )
    assert result.posts_classified == 6
    assert result.errors == {}

    tax = get_taxonomies()
    rows = PostIntelligenceRepo(db_session).list_for_run(run_id)
    assert len(rows) == 6
    for row in rows:
        assert row.format in tax.formats
        assert row.topic in tax.topics
        assert row.cta in tax.cta_types
        for kw in row.keywords or []:
            assert kw["category"] in tax.keyword_categories
        assert row.prompt_versions == graph_mod.current_prompt_versions(prompt_registry)


def test_rerun_is_a_cache_hit(db_session, classify_router, prompt_registry, fake_llm):
    run_id = _seed_run(db_session, 4)
    classify_posts_for_run(
        db_session, run_id=run_id, router=classify_router, registry=prompt_registry
    )
    calls_after_first = len(fake_llm.calls)

    second = classify_posts_for_run(
        db_session, run_id=run_id, router=classify_router, registry=prompt_registry
    )
    assert second.posts_classified == 0
    assert second.posts_to_classify == 0
    assert second.cache_hits == 4
    assert len(fake_llm.calls) == calls_after_first  # zero new LLM calls


def test_prompt_version_bump_reprocesses(db_session, classify_router, prompt_registry, monkeypatch):
    run_id = _seed_run(db_session, 3)
    classify_posts_for_run(
        db_session, run_id=run_id, router=classify_router, registry=prompt_registry
    )

    bumped = {**graph_mod.current_prompt_versions(prompt_registry), "topic_classify": 2}
    monkeypatch.setattr(graph_mod, "current_prompt_versions", lambda _registry: bumped)

    reprocessed = classify_posts_for_run(
        db_session, run_id=run_id, router=classify_router, registry=prompt_registry
    )
    assert reprocessed.posts_classified == 3
    stored = PostIntelligenceRepo(db_session).list_for_run(run_id)
    assert [row.prompt_versions for row in stored] == [bumped, bumped, bumped]


def test_batch_of_ten_is_one_call_per_task(db_session, classify_router, prompt_registry, fake_llm):
    run_id = _seed_run(db_session, 10)
    classify_posts_for_run(
        db_session, run_id=run_id, router=classify_router, registry=prompt_registry
    )
    by_schema: dict[str, int] = {}
    for call in fake_llm.calls:
        by_schema[call["schema"]] = by_schema.get(call["schema"], 0) + 1
    assert by_schema["FormatClassification"] == 1
    assert by_schema["TopicClassification"] == 1
    assert by_schema["CtaClassification"] == 1
    assert by_schema["KeywordClassification"] == 1


def test_tfidf_terms_merged_with_source_tag(db_session, classify_router, prompt_registry):
    run_id = _seed_run(db_session, 6)
    classify_posts_for_run(
        db_session, run_id=run_id, router=classify_router, registry=prompt_registry
    )
    rows = PostIntelligenceRepo(db_session).list_for_run(run_id)
    tfidf_tags = [kw for row in rows for kw in (row.keywords or []) if kw.get("source") == "tfidf"]
    llm_tags = [kw for row in rows for kw in (row.keywords or []) if kw.get("source") == "llm"]
    assert tfidf_tags  # TF-IDF recovered terms the fake LLM omitted
    assert llm_tags


def test_unknown_taxonomy_value_is_rejected_then_repaired(
    db_session, settings, models_config, fake_llm, prompt_registry
):
    run_id = _seed_run(db_session, 1)
    register_classification_fakes(fake_llm)
    # First format response invents a value -> schema rejects -> router repair round-trip.
    fake_llm.enqueue('{"results": [{"index": 0, "format": "totally_bogus"}]}')
    fake_llm.enqueue('{"results": [{"index": 0, "format": "video"}]}')
    router = ModelRouter(settings, models_config, fake_llm=fake_llm, backoff_base=0)

    result = classify_posts_for_run(
        db_session, run_id=run_id, router=router, registry=prompt_registry
    )
    assert result.posts_classified == 1
    row = PostIntelligenceRepo(db_session).list_for_run(run_id)[0]
    assert row.format == "video"
    fmt_calls = [c for c in fake_llm.calls if c["schema"] == "FormatClassification"]
    assert len(fmt_calls) == 2  # bad payload + repair
