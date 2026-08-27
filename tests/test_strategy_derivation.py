"""Signal-stamping derivation rules (EPIC-06): reproducible, data-driven, LLM-overriding."""

from app.config.settings import get_company_context
from app.schemas.strategy import ContentOpportunity, ContentStrategy
from app.schemas.strategy_map import CrossCompetitorInsights, TopContentReport
from app.strategy.derivation import (
    derive_competition_level,
    derive_competitor_signal,
    derive_engagement_potential,
    stamp_signals,
)
from app.strategy.fakes import register_strategy_fakes
from app.strategy.generator import StrategyConfig, step_opportunities
from app.strategy.inputs import StrategyInputs, TopicStat

_CFG = {
    "signal_topic_share_high": 0.15,
    "signal_topic_share_med": 0.05,
    "competition_competitors_high": 3,
    "competition_competitors_med": 2,
}


def _stat(**kw) -> TopicStat:
    base = dict(
        topic="ai",
        post_count=10,
        post_share=0.2,
        competitors_covering=3,
        avg_engagement=100.0,
        above_median_engagement=True,
        is_opportunity=False,
        is_white_space=False,
    )
    base.update(kw)
    return TopicStat(**base)


def test_competitor_signal_bands_on_share():
    assert derive_competitor_signal(_stat(post_share=0.20), _CFG) == "high"
    assert derive_competitor_signal(_stat(post_share=0.08), _CFG) == "medium"
    assert derive_competitor_signal(_stat(post_share=0.01), _CFG) == "low"
    assert derive_competitor_signal(None, _CFG) == "low"


def test_competition_level_bands_on_coverage():
    assert derive_competition_level(_stat(competitors_covering=4), _CFG) == "high"
    assert derive_competition_level(_stat(competitors_covering=2), _CFG) == "medium"
    assert derive_competition_level(_stat(competitors_covering=1), _CFG) == "low"


def test_engagement_potential_uses_quadrant_flags():
    assert derive_engagement_potential(_stat(is_opportunity=True), _CFG) == "high"
    assert derive_engagement_potential(_stat(is_white_space=True), _CFG) == "high"
    assert (
        derive_engagement_potential(_stat(is_opportunity=False, above_median_engagement=True), _CFG)
        == "medium"
    )
    assert (
        derive_engagement_potential(
            _stat(is_opportunity=False, above_median_engagement=False), _CFG
        )
        == "low"
    )


def test_stamp_signals_is_case_insensitive_and_complete():
    stats = {"ai": _stat(post_share=0.3, competitors_covering=4, is_opportunity=True)}
    assert stamp_signals("AI", stats, _CFG) == {
        "competitor_signal": "high",
        "competition_level": "high",
        "engagement_potential": "high",
    }


class _LyingAgent:
    """Proposes 'low' for every signal; the derivation must overwrite from data."""

    def opportunities(self, inputs, strategy, *, omin, omax):
        return [
            ContentOpportunity(
                topic="ai",
                pillar="P",
                competitor_signal="low",
                competition_level="low",
                engagement_potential="low",
                recommended_format="thought_leadership",
                target_audience="ops",
                hook="an entirely original hook about applied ai for operators here",
                angle="an original operator angle on applied ai that nobody else runs",
                key_message="ship small, measure everything, and let the dashboards decide",
                structure=["a", "b"],
                cta="learn_more",
                keywords=["ai"],
                hashtags=["ai"],
            )
        ]

    def regenerate_field(self, inputs, opp, field, reason):
        return "fresh original replacement line with zero competitor overlap"


def test_step_opportunities_overrides_agent_signal(fake_router, fake_llm, prompt_registry):
    register_strategy_fakes(fake_llm)
    inputs = StrategyInputs(
        run_id=1,
        company=get_company_context(),
        profiles=[],
        cross=CrossCompetitorInsights(),
        top_content=TopContentReport(ranked_by="engagement_score"),
        campaigns=[],
        competitor_texts=["something completely unrelated"],
        topic_stats={"ai": _stat(post_share=0.3, competitors_covering=4, is_opportunity=True)},
        n_competitors=4,
    )
    opps, _checks = step_opportunities(
        inputs,
        _LyingAgent(),
        ContentStrategy(pillars=[], content_mix={}),
        router=fake_router,
        registry=prompt_registry,
        cfg=StrategyConfig.from_app(None),
    )
    assert opps[0].competitor_signal == "high"
    assert opps[0].competition_level == "high"
    assert opps[0].engagement_potential == "high"
