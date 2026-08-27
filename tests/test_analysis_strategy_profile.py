"""StrategyProfile against a hand-computed fixture (EPIC-05). Only positioning_summary
touches the LLM (fake); every other field is deterministic arithmetic."""

from datetime import datetime

import pytest

from app.analysis.engagement import score_run
from app.analysis.mapping_fakes import register_mapping_fakes
from app.analysis.strategy_profile import build_strategy_profiles
from app.db.repos import CompetitorRepo, PostIntelligenceRepo, PostRepo, ProfileRepo, RunRepo
from app.schemas.collection import CompanyProfile, RawPost
from app.schemas.intelligence import KeywordTag, PostClassification

# key, format, topic, date (weekday), reactions   (comments/reposts 0 -> score == reactions)
_POSTS = [
    ("p0", "carousel", "ai", datetime(2026, 1, 7, 9), 500),  # Wed
    ("p1", "carousel", "ai", datetime(2026, 1, 7, 11), 400),  # Wed
    ("p2", "carousel", "cloud", datetime(2026, 1, 6, 9), 300),  # Tue
    ("p3", "text_only", "ai", datetime(2026, 1, 6, 12), 100),  # Tue
    ("p4", "text_only", "ai", datetime(2026, 1, 5, 9), 80),  # Mon
    ("p5", "text_only", "cloud", datetime(2026, 1, 5, 15), 60),  # Mon
    ("p6", "blog_article", "cloud", datetime(2026, 1, 8, 9), 50),  # Thu
    ("p7", "blog_article", "other", datetime(2026, 1, 9, 9), 40),  # Fri
]


@pytest.fixture
def profiled_run(db_session, fake_llm):
    register_mapping_fakes(fake_llm)
    comp = CompetitorRepo(db_session).upsert(
        name="Acme", linkedin_url="https://www.linkedin.com/company/acme"
    )
    ProfileRepo(db_session).upsert(comp.id, CompanyProfile(followers=10_000))
    run = RunRepo(db_session).create(period_days=28, adapter="mock")
    for i, (key, fmt, topic, when, reactions) in enumerate(_POSTS):
        created = PostRepo(db_session).insert_new(
            run_id=run.id,
            competitor_id=comp.id,
            source_adapter="mock",
            posts=[
                RawPost(
                    url=f"https://example.test/{key}",
                    posted_at=when,
                    content=f"{key} about {topic}",
                    media_type="text",
                    reactions=reactions,
                    comments=0,
                    reposts=0,
                )
            ],
        )
        PostIntelligenceRepo(db_session).upsert(
            created[0].id,
            PostClassification(
                index=i,
                format=fmt,
                topic=topic,
                sub_topic=None,
                cta="none",
                keywords=[KeywordTag(term=topic, category="industry_term")],
            ),
            hashtags=[],
            prompt_versions={"format_classify": 1},
        )
    db_session.commit()
    score_run(db_session, run_id=run.id)
    db_session.commit()
    return run.id, comp.id


def test_profile_reproduces_hand_computed_values(db_session, profiled_run, fake_router):
    run_id, comp_id = profiled_run
    result = build_strategy_profiles(
        db_session, run_id=run_id, router=fake_router, registry=_registry()
    )
    assert len(result.profiles) == 1
    prof = result.profiles[0]

    assert prof.competitor_id == comp_id
    assert prof.primary_themes == ["ai", "cloud", "other"]
    assert prof.best_format == "carousel"
    assert prof.best_topic == "ai"
    assert prof.posting_frequency_per_week == pytest.approx(2.0)
    assert prof.engagement_windows == ["Wed", "Tue", "Mon"]
    assert prof.positioning_summary  # fake produced something

    assert prof.content_mix["visual"] == pytest.approx(37.5)
    assert prof.content_mix["text"] == pytest.approx(37.5)
    assert prof.content_mix["long_form"] == pytest.approx(25.0)
    assert sum(prof.content_mix.values()) == pytest.approx(100.0, abs=1.0)


def test_best_format_respects_min_sample(db_session, profiled_run, fake_router):
    run_id, _ = profiled_run
    prof = build_strategy_profiles(
        db_session, run_id=run_id, router=fake_router, registry=_registry()
    ).profiles[0]
    # blog_article has only 2 posts -> never eligible to be "best" despite existing
    assert prof.best_format != "blog_article"


def _registry():
    from app.config.settings import PROMPTS_DIR
    from app.core.prompt_registry import PromptRegistry

    return PromptRegistry(PROMPTS_DIR)
