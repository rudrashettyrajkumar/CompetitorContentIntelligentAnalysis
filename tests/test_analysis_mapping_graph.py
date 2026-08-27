"""EPIC-05 mapping stage end-to-end: profiles -> cross -> top_content, persisted."""

from datetime import datetime

import pytest

from app.analysis.graph import analyze_run
from app.analysis.mapping_fakes import register_mapping_fakes
from app.analysis.mapping_graph import map_strategy_run
from app.core.model_router import ModelRouter
from app.datasources.collector import collect_for_run
from app.datasources.mock import MockAdapter
from app.db.repos import CompetitorRepo, InsightRepo, RunRepo, StrategyProfileRepo
from app.intelligence.fakes import register_classification_fakes
from app.intelligence.graph import classify_posts_for_run

NOW = datetime(2026, 3, 15, 12, 0)


@pytest.fixture
def full_router(settings, models_config, fake_llm):
    register_classification_fakes(fake_llm)
    register_mapping_fakes(fake_llm)
    return ModelRouter(settings, models_config, fake_llm=fake_llm, backoff_base=0)


def _analysed_run(session, router, registry):
    repo = CompetitorRepo(session)
    competitors = [
        repo.upsert(name="Acme", linkedin_url="https://www.linkedin.com/company/acme"),
        repo.upsert(name="Beta", linkedin_url="https://www.linkedin.com/company/beta-corp"),
        repo.upsert(name="Gamma", linkedin_url="https://www.linkedin.com/company/gamma-io"),
    ]
    run = RunRepo(session).create(period_days=30, adapter="mock")
    collect_for_run(
        session,
        run_id=run.id,
        competitors=competitors,
        adapter=MockAdapter(now=NOW),
        period_days=30,
        now=NOW,
    )
    session.commit()
    classify_posts_for_run(session, run_id=run.id, router=router, registry=registry)
    session.commit()
    analyze_run(session, run_id=run.id, router=router, registry=registry)
    session.commit()
    return run.id


def test_mapping_run_persists_profiles_and_insights(db_session, full_router, prompt_registry):
    run_id = _analysed_run(db_session, full_router, prompt_registry)

    result = map_strategy_run(
        db_session, run_id=run_id, router=full_router, registry=prompt_registry
    )

    # one profile per competitor, persisted
    assert len(result.profiles.profiles) == 3
    assert StrategyProfileRepo(db_session).count_for_run(run_id) == 3
    for prof in result.profiles.profiles:
        assert prof.positioning_summary
        assert (
            sum(prof.content_mix.values()) == pytest.approx(100.0, abs=1.0) or not prof.content_mix
        )

    # cross + top_content bundles persisted as insights
    repo = InsightRepo(db_session)
    cross = repo.get_payload(run_id, "cross_competitor")
    top = repo.get_payload(run_id, "top_content")
    assert cross is not None and "keyword_matrix" in cross
    assert top is not None and len(top["items"]) >= 1
    assert all(item["why"]["summary"] for item in top["items"])

    assert RunRepo(db_session).get(run_id).stage == "top_content"


def test_mapping_run_is_rerunnable(db_session, full_router, prompt_registry):
    run_id = _analysed_run(db_session, full_router, prompt_registry)
    map_strategy_run(db_session, run_id=run_id, router=full_router, registry=prompt_registry)
    map_strategy_run(db_session, run_id=run_id, router=full_router, registry=prompt_registry)
    # replace-for-run semantics: still exactly one profile per competitor
    assert StrategyProfileRepo(db_session).count_for_run(run_id) == 3
    assert len(InsightRepo(db_session).list_for_run(run_id)) == 2
