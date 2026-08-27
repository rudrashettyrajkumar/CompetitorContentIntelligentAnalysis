"""EPIC-06 strategy stage end-to-end on mock data: pillars -> opportunities -> calendar."""

from datetime import datetime

import pytest

from app.analysis.graph import analyze_run
from app.analysis.mapping_fakes import register_mapping_fakes
from app.analysis.mapping_graph import map_strategy_run
from app.core.model_router import ModelRouter
from app.datasources.collector import collect_for_run
from app.datasources.mock import MockAdapter
from app.db.repos import CompetitorRepo, InsightRepo, RunRepo
from app.intelligence.fakes import register_classification_fakes
from app.intelligence.graph import classify_posts_for_run
from app.strategy.fakes import register_strategy_fakes
from app.strategy.graph import run_strategy_stage

NOW = datetime(2026, 3, 15, 12, 0)


@pytest.fixture
def everything_router(settings, models_config, fake_llm):
    register_classification_fakes(fake_llm)
    register_mapping_fakes(fake_llm)
    register_strategy_fakes(fake_llm)
    return ModelRouter(settings, models_config, fake_llm=fake_llm, backoff_base=0)


@pytest.fixture
def mapped_run(db_session, everything_router, prompt_registry):
    repo = CompetitorRepo(db_session)
    competitors = [
        repo.upsert(name="Acme", linkedin_url="https://www.linkedin.com/company/acme"),
        repo.upsert(name="Beta", linkedin_url="https://www.linkedin.com/company/beta-corp"),
        repo.upsert(name="Gamma", linkedin_url="https://www.linkedin.com/company/gamma-io"),
    ]
    run = RunRepo(db_session).create(period_days=30, adapter="mock")
    collect_for_run(
        db_session,
        run_id=run.id,
        competitors=competitors,
        adapter=MockAdapter(now=NOW),
        period_days=30,
        now=NOW,
    )
    db_session.commit()
    classify_posts_for_run(
        db_session, run_id=run.id, router=everything_router, registry=prompt_registry
    )
    db_session.commit()
    analyze_run(db_session, run_id=run.id, router=everything_router, registry=prompt_registry)
    db_session.commit()
    map_strategy_run(db_session, run_id=run.id, router=everything_router, registry=prompt_registry)
    db_session.commit()
    return run.id


def test_strategy_stage_produces_valid_bundle(
    db_session, mapped_run, everything_router, prompt_registry
):
    result = run_strategy_stage(
        db_session, run_id=mapped_run, router=everything_router, registry=prompt_registry
    )
    sb = result.bundle

    assert 4 <= len(sb.strategy.pillars) <= 6
    for p in sb.strategy.pillars:
        assert p.rationale.strip()  # every pillar cites a signal / white space
    assert sum(sb.strategy.content_mix.values()) == pytest.approx(100.0, abs=1.0)

    assert 8 <= len(sb.opportunities) <= 12
    for op in sb.opportunities:
        assert op.hook and op.angle and op.key_message and op.structure and op.cta
        assert op.competitor_signal in ("high", "medium", "low")
        assert op.recommended_format
        assert op.pillar in {p.name for p in sb.strategy.pillars} or op.pillar

    assert result.calendar_valid, result.calendar_errors
    days = [e.day for e in sb.calendar.entries]
    assert days == sorted(days) and min(days) >= 1 and max(days) <= 30
    assert all(e.pillar in {p.name for p in sb.strategy.pillars} for e in sb.calendar.entries)


def test_strategy_stage_persists_three_insight_kinds(
    db_session, mapped_run, everything_router, prompt_registry
):
    run_strategy_stage(
        db_session, run_id=mapped_run, router=everything_router, registry=prompt_registry
    )
    repo = InsightRepo(db_session)
    assert repo.get_payload(mapped_run, "strategy") is not None
    opp_payload = repo.get_payload(mapped_run, "opportunities")
    assert opp_payload and 8 <= len(opp_payload["opportunities"]) <= 12
    assert "originality_checks" in opp_payload
    cal_payload = repo.get_payload(mapped_run, "calendar")
    assert cal_payload and cal_payload["valid"] is True
    assert len(cal_payload["calendar"]["entries"]) >= 10
    assert RunRepo(db_session).get(mapped_run).stage == "calendar"


def test_strategy_stage_is_rerunnable(db_session, mapped_run, everything_router, prompt_registry):
    run_strategy_stage(
        db_session, run_id=mapped_run, router=everything_router, registry=prompt_registry
    )
    run_strategy_stage(
        db_session, run_id=mapped_run, router=everything_router, registry=prompt_registry
    )
    kinds = [i.kind for i in InsightRepo(db_session).list_for_run(mapped_run)]
    # cross_competitor + top_content (EPIC-05) + strategy + opportunities + calendar
    assert sorted(kinds) == [
        "calendar",
        "cross_competitor",
        "opportunities",
        "strategy",
        "top_content",
    ]
