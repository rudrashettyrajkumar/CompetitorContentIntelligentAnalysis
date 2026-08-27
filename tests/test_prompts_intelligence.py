"""Render + parse coverage for the four EPIC-03 classification prompt packs."""

import pytest

from app.config.settings import get_taxonomies
from app.intelligence.fakes import register_classification_fakes

PACKS = ["format_classify", "topic_classify", "cta_extract", "keyword_extract"]

SAMPLE_POSTS = [
    {"index": 0, "media_type": "video", "content": "Watch our webinar on cloud automation."},
    {"index": 1, "media_type": "image", "content": "Behind the scenes of our hiring push."},
]


def _vars_for(pack: str) -> dict:
    tax = get_taxonomies()
    if pack == "format_classify":
        return {"posts": SAMPLE_POSTS, "taxonomy": tax.formats}
    if pack == "topic_classify":
        return {"posts": SAMPLE_POSTS, "taxonomy": tax.topics}
    if pack == "cta_extract":
        return {"posts": SAMPLE_POSTS, "taxonomy": tax.cta_types}
    return {"posts": SAMPLE_POSTS, "categories": tax.keyword_categories}


@pytest.mark.parametrize("pack", PACKS)
def test_pack_registered_and_batched(prompt_registry, pack):
    spec = prompt_registry.get(pack)
    assert spec.meta.batch is True
    assert spec.meta.model_tier == "fast"
    assert spec.meta.temperature <= 0.2


@pytest.mark.parametrize("pack", PACKS)
def test_pack_renders_with_sample_vars(prompt_registry, pack):
    rendered = prompt_registry.render(pack, **_vars_for(pack))
    assert rendered.system.strip()
    # every post shows up as an indexed line the fake responders can parse back
    assert "[0] media=video ::" in rendered.user
    assert "[1] media=image ::" in rendered.user


@pytest.mark.parametrize("pack", PACKS)
def test_pack_parses_fake_response(prompt_registry, fake_router, fake_llm, pack):
    register_classification_fakes(fake_llm)
    rendered = prompt_registry.render(pack, **_vars_for(pack))
    result = fake_router.invoke(
        tier=rendered.meta.model_tier,
        system=rendered.system,
        user=rendered.user,
        schema=rendered.schema,
        temperature=rendered.meta.temperature,
        prompt_name=rendered.meta.name,
        prompt_version=rendered.meta.version,
    )
    assert {r.index for r in result.results} == {0, 1}
