"""Originality guard (EPIC-06): planted near-copy rejected, regeneration path, verdicts."""

import pytest

from app.strategy.fakes import register_strategy_fakes
from app.strategy.originality import OverlapIndex, run_originality_guard

_COMPETITOR_TEXTS = [
    "We are thrilled to announce our new AI-powered analytics suite that helps teams "
    "cut reporting time in half and make faster decisions across the whole business.",
    "Join our upcoming webinar on cloud migration best practices for regulated industries.",
    "Our customers tell us that onboarding speed is the single biggest driver of renewal.",
]

_CFG = {"originality_ngram": 6, "originality_max_overlap": 0.30, "originality_regen_attempts": 1}


def _opp(
    hook: str,
    angle: str = "a distinct angle unlike anything competitors publish here",
    key_message: str = "a unique operator message about measurable outcomes and speed",
):
    from app.schemas.strategy import ContentOpportunity

    return ContentOpportunity(
        topic="ai",
        pillar="P",
        recommended_format="thought_leadership",
        target_audience="ops leaders",
        hook=hook,
        angle=angle,
        key_message=key_message,
        structure=["x"],
        cta="learn_more",
        keywords=["ai"],
        hashtags=["ai"],
    )


@pytest.fixture
def router(fake_router, fake_llm):
    register_strategy_fakes(fake_llm)
    return fake_router


def test_overlap_index_scores_near_copy_high():
    idx = OverlapIndex.build(_COMPETITOR_TEXTS, 6)
    near_copy = (
        "We are thrilled to announce our new AI-powered analytics suite that helps teams "
        "cut reporting time in half"
    )
    assert idx.overlap_ratio(near_copy) > 0.30
    assert (
        idx.overlap_ratio("A wholly different sentence about operator playbooks and proof") == 0.0
    )


def test_planted_near_copy_is_rejected_by_ngram(router, prompt_registry):
    near_copy = (
        "We are thrilled to announce our new AI-powered analytics suite that helps teams "
        "cut reporting time in half and make faster decisions"
    )
    opps = [
        _opp(hook="a perfectly fine original hook about applied ai for operators"),
        _opp(hook=near_copy),
    ]
    result = run_originality_guard(
        opps,
        _COMPETITOR_TEXTS,
        router=router,
        registry=prompt_registry,
        cfg=_CFG,
        regenerate=None,  # cannot regenerate -> must be dropped
    )
    assert len(result.opportunities) == 1
    verdicts = {(c.opportunity_index, c.field): c.verdict for c in result.checks}
    assert verdicts[(1, "hook")] == "dropped"
    dropped = [c for c in result.checks if c.verdict == "dropped"]
    assert dropped and dropped[0].overlap_ratio is not None and dropped[0].overlap_ratio > 0.30


def test_regeneration_path_recovers_the_opportunity(router, prompt_registry):
    near_copy = (
        "We are thrilled to announce our new AI-powered analytics suite that helps teams "
        "cut reporting time in half and make faster decisions"
    )
    opps = [_opp(hook=near_copy)]

    def regen(oi, field, reason):
        return "An operator's field notes on applied AI: three calls we got wrong first"

    result = run_originality_guard(
        opps,
        _COMPETITOR_TEXTS,
        router=router,
        registry=prompt_registry,
        cfg=_CFG,
        regenerate=regen,
    )
    assert len(result.opportunities) == 1
    assert result.opportunities[0].hook.startswith("An operator's field notes")
    regen_checks = [c for c in result.checks if c.verdict == "regenerated"]
    assert regen_checks and regen_checks[0].field == "hook"


def test_llm_layer_catches_rewrite_the_ngram_check_misses(router, prompt_registry):
    # threshold set absurdly high so the deterministic layer never fires;
    # the fake LLM judge flags a 4+ word shared run.
    cfg = dict(_CFG, originality_max_overlap=0.99)
    opps = [_opp(hook="onboarding speed is the single biggest driver of something else entirely")]
    result = run_originality_guard(
        opps,
        _COMPETITOR_TEXTS,
        router=router,
        registry=prompt_registry,
        cfg=cfg,
        regenerate=None,
    )
    assert result.opportunities == []
    assert any(c.verdict == "dropped" and "run" in c.detail for c in result.checks)


def test_clean_opportunities_all_pass(router, prompt_registry):
    opps = [
        _opp(hook=f"Original operator hook {i} about a niche workflow nobody blogs about")
        for i in range(3)
    ]
    result = run_originality_guard(
        opps,
        _COMPETITOR_TEXTS,
        router=router,
        registry=prompt_registry,
        cfg=_CFG,
        regenerate=None,
    )
    assert len(result.opportunities) == 3
    assert {c.verdict for c in result.checks} == {"ok"}
    assert len(result.checks) == 9  # 3 opps x 3 guarded fields
