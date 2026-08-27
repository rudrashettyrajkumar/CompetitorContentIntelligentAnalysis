"""Render + parse coverage for the EPIC-05 analysis prompt packs."""

import pytest

from app.analysis.mapping_fakes import register_mapping_fakes
from app.core.model_router import ModelRouter
from app.schemas.strategy_map import PositioningSummary, WhyItWorkedBatch


@pytest.fixture
def router(settings, models_config, fake_llm):
    register_mapping_fakes(fake_llm)
    return ModelRouter(settings, models_config, fake_llm=fake_llm, backoff_base=0)


def test_positioning_summary_renders_and_parses(prompt_registry, router):
    rendered = prompt_registry.render(
        "positioning_summary",
        competitor="Acme",
        primary_themes=["ai", "cloud"],
        content_mix={"visual": 40.0, "text": 60.0},
        best_format="carousel",
        best_topic="ai",
        posting_frequency_per_week=3.5,
        engagement_windows=["Tue", "Wed"],
    )
    assert "Acme" in rendered.user
    out = router.invoke(
        tier=rendered.meta.model_tier,
        system=rendered.system,
        user=rendered.user,
        schema=rendered.schema,
    )
    assert isinstance(out, PositioningSummary)
    assert "Acme" in out.summary


def test_why_it_worked_batch_renders_and_parses(prompt_registry, router):
    posts = [
        {
            "index": i,
            "competitor": "Acme",
            "format": "carousel",
            "topic": "ai",
            "date": "2026-01-05",
            "engagement_score": 500 + i,
            "content": f"How we cut onboarding time by 40% — a customer story number {i}?",
        }
        for i in range(5)
    ]
    rendered = prompt_registry.render("why_it_worked", posts=posts)
    out = router.invoke(
        tier=rendered.meta.model_tier,
        system=rendered.system,
        user=rendered.user,
        schema=rendered.schema,
    )
    assert isinstance(out, WhyItWorkedBatch)
    assert {r.index for r in out.results} == set(range(5))
    for r in out.results:
        assert r.summary and r.hook and r.visual_format
