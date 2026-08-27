"""Render + parse coverage for the campaign_cluster prompt pack (EPIC-04)."""

from app.analysis.fakes import register_campaign_fakes
from app.schemas.analysis import CampaignClustering

SAMPLE_POSTS = [
    {
        "index": i,
        "url": f"https://example.test/p{i}",
        "date": f"2026-03-0{i + 1}",
        "format": "thought_leadership",
        "topic": "ai",
        "sub_topic": "AI for Manufacturing",
        "cta": "learn_more",
        "score": 100 + i,
        "keywords": ["ai", "manufacturing"],
        "hashtags": ["ai"],
    }
    for i in range(4)
]


def _vars():
    return {"competitor": "Acme", "posts": SAMPLE_POSTS, "min_posts": 3, "window_days": 30}


def test_pack_registered_as_reasoning_batch(prompt_registry):
    spec = prompt_registry.get("campaign_cluster")
    assert spec.meta.model_tier == "reasoning"
    assert spec.meta.batch is True
    assert spec.schema is CampaignClustering


def test_pack_renders_with_sample_vars(prompt_registry):
    rendered = prompt_registry.render("campaign_cluster", **_vars())
    assert rendered.system.strip()
    assert "[0]" in rendered.user and "[3]" in rendered.user
    assert "https://example.test/p0" in rendered.user
    assert "min_posts" not in rendered.user  # variable was substituted, not left literal


def test_pack_parses_fake_response(prompt_registry, fake_router, fake_llm):
    register_campaign_fakes(fake_llm)
    rendered = prompt_registry.render("campaign_cluster", **_vars())
    result = fake_router.invoke(
        tier=rendered.meta.model_tier,
        system=rendered.system,
        user=rendered.user,
        schema=rendered.schema,
        temperature=rendered.meta.temperature,
        prompt_name=rendered.meta.name,
        prompt_version=rendered.meta.version,
    )
    assert isinstance(result, CampaignClustering)
    assert len(result.campaigns) == 1
    assert result.campaigns[0].post_urls == [p["url"] for p in SAMPLE_POSTS]


def test_router_repairs_invalid_campaign_json(prompt_registry, fake_router, fake_llm):
    fake_llm.enqueue('{"campaigns": [{"name": 123}]}')  # name wrong type, missing theme
    fake_llm.enqueue('{"campaigns": []}')
    rendered = prompt_registry.render("campaign_cluster", **_vars())
    result = fake_router.invoke(
        tier=rendered.meta.model_tier,
        system=rendered.system,
        user=rendered.user,
        schema=rendered.schema,
        temperature=rendered.meta.temperature,
        prompt_name=rendered.meta.name,
        prompt_version=rendered.meta.version,
    )
    assert result.campaigns == []
    assert len([c for c in fake_llm.calls if c["schema"] == "CampaignClustering"]) == 2
