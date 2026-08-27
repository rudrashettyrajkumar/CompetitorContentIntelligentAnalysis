"""Render + parse for the EPIC-08 change_report prompt."""

import pytest

from app.core.model_router import ModelRouter
from app.scheduler.fakes import register_loop_fakes
from app.schemas.loop import ChangeReport, PeriodDiff


@pytest.fixture
def router(settings, models_config, fake_llm):
    register_loop_fakes(fake_llm)
    return ModelRouter(settings, models_config, fake_llm=fake_llm, backoff_base=0)


def test_change_report_renders_and_parses(prompt_registry, router):
    diff = PeriodDiff(
        baseline_run_id=1,
        current_run_id=2,
        new_posts=40,
        posts_delta_pct=25.0,
        new_campaigns=["AI blitz"],
    )
    rendered = prompt_registry.render("change_report", diff=diff.model_dump(mode="json"))
    assert "run 1" in rendered.user and "run 2" in rendered.user
    out = router.invoke(
        tier=rendered.meta.model_tier,
        system=rendered.system,
        user=rendered.user,
        schema=rendered.schema,
    )
    assert isinstance(out, ChangeReport)
    assert out.narrative and out.headline
