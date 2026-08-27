"""Render + parse coverage for the EPIC-06 strategy prompt packs."""

import pytest

from app.core.model_router import ModelRouter
from app.schemas.strategy import (
    ContentCalendar,
    ContentOpportunityList,
    ContentStrategy,
    OriginalityVerdict,
    RegeneratedField,
)
from app.strategy.fakes import register_strategy_fakes


def _company():
    from app.config.settings import get_company_context

    return get_company_context().model_dump()


@pytest.fixture
def router(settings, models_config, fake_llm):
    register_strategy_fakes(fake_llm)
    return ModelRouter(settings, models_config, fake_llm=fake_llm, backoff_base=0)


def _invoke(registry, router, name, **variables):
    rendered = registry.render(name, **variables)
    return router.invoke(
        tier=rendered.meta.model_tier,
        system=rendered.system,
        user=rendered.user,
        schema=rendered.schema,
    )


def test_pillars_prompt(prompt_registry, router):
    out = _invoke(
        prompt_registry,
        router,
        "pillars",
        company=_company(),
        profiles=[],
        cross={},
        top_content={},
        campaigns=[],
        pillars_min=4,
        pillars_max=6,
    )
    assert isinstance(out, ContentStrategy)
    assert 4 <= len(out.pillars) <= 6
    assert sum(out.content_mix.values()) == pytest.approx(100.0, abs=1.0)


def test_opportunities_prompt(prompt_registry, router):
    out = _invoke(
        prompt_registry,
        router,
        "opportunities",
        company=_company(),
        strategy={},
        cross={},
        topic_stats={},
        keyword_terms=["ai", "rev ops"],
        opportunities_min=8,
        opportunities_max=12,
        taxonomy_formats=["thought_leadership", "carousel"],
    )
    assert isinstance(out, ContentOpportunityList)
    assert len(out.opportunities) >= 8


def test_calendar_prompt(prompt_registry, router):
    out = _invoke(
        prompt_registry,
        router,
        "calendar",
        company=_company(),
        strategy={},
        opportunities=[],
        calendar_days=30,
    )
    assert isinstance(out, ContentCalendar)
    assert out.entries and all(1 <= e.day <= 30 for e in out.entries)


def test_originality_check_prompt(prompt_registry, router):
    out = _invoke(
        prompt_registry,
        router,
        "originality_check",
        candidates=[
            {"index": 0, "text": "onboarding speed is the single biggest driver of renewal"}
        ],
        excerpts=[
            "our customers tell us that onboarding speed is the single biggest driver of renewal"
        ],
    )
    assert isinstance(out, OriginalityVerdict)
    assert out.results[0].is_rewrite is True


def test_regenerate_field_prompt(prompt_registry, router):
    out = _invoke(
        prompt_registry,
        router,
        "regenerate_field",
        company=_company(),
        topic="automation",
        field="hook",
        reason="too similar",
        current="the old hook",
    )
    assert isinstance(out, RegeneratedField)
    assert out.text
