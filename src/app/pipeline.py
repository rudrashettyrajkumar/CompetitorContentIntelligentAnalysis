"""Full intelligence pipeline (EPIC-07): collect → classify → analyze → map → strategy.

One entrypoint, ``run_pipeline``, used by the API background task and (EPIC-08) the
scheduler. It owns its own DB session, records a wall-clock timing per stage on the
``runs`` row, and turns any failure into ``status = failed`` with the error text rather
than raising. Offline it uses ``FakeLLM`` with every stage's fakes registered, so a
``LLM_FAKE_MODE`` server runs the whole thing with zero quota.
"""

from __future__ import annotations

import time
from contextlib import contextmanager

from sqlalchemy.orm import Session, sessionmaker

from app.analysis.graph import analyze_run
from app.analysis.mapping_fakes import register_mapping_fakes
from app.analysis.mapping_graph import map_strategy_run
from app.config.settings import PROMPTS_DIR, get_app_config, get_models_config, get_settings
from app.core.logging import get_logger
from app.core.model_router import FakeLLM, ModelRouter
from app.core.prompt_registry import PromptRegistry
from app.datasources.base import get_datasource
from app.datasources.collector import collect_for_run
from app.db.repos import CompetitorRepo, RunRepo
from app.intelligence.fakes import register_classification_fakes
from app.intelligence.graph import classify_posts_for_run
from app.strategy.fakes import register_strategy_fakes
from app.strategy.graph import run_strategy_stage

log = get_logger(__name__)


def build_pipeline_router(settings=None, models_config=None) -> ModelRouter:
    """A ModelRouter with every stage's FakeLLM responder registered when in fake mode."""
    settings = settings or get_settings()
    models_config = models_config or get_models_config()
    fake = FakeLLM()
    router = ModelRouter(settings, models_config, fake_llm=fake)
    if router.use_fake:
        register_classification_fakes(fake)
        register_mapping_fakes(fake)
        register_strategy_fakes(fake)
    return router


@contextmanager
def _stage(session: Session, run_id: int, name: str):
    started = time.monotonic()
    try:
        yield
    finally:
        RunRepo(session).record_timing(run_id, name, time.monotonic() - started)
        session.commit()


def run_pipeline(session_factory: sessionmaker, run_id: int) -> None:
    """Execute every stage for ``run_id``. Never raises — failures land on the run row."""
    session: Session = session_factory()
    app_config = get_app_config()
    registry = PromptRegistry(PROMPTS_DIR)
    router = build_pipeline_router()
    try:
        run = RunRepo(session).get(run_id)
        if run is None:
            log.warning("pipeline_unknown_run", run_id=run_id)
            return
        competitor_repo = CompetitorRepo(session)
        if run.competitor_ids:
            competitors = [
                c for cid in run.competitor_ids if (c := competitor_repo.get(cid)) is not None
            ]
        else:
            competitors = competitor_repo.list_all(status="active")
        if not competitors:
            RunRepo(session).finish(run_id, error="no competitors to analyse")
            session.commit()
            return

        adapter = get_datasource(run.adapter, get_settings(), app_config)

        with _stage(session, run_id, "collect"):
            RunRepo(session).set_stage(run_id, "collect")
            collect_for_run(
                session,
                run_id=run_id,
                competitors=competitors,
                adapter=adapter,
                period_days=run.period_days,
            )
        with _stage(session, run_id, "classify"):
            classify_posts_for_run(session, run_id=run_id, router=router, registry=registry)
        with _stage(session, run_id, "analyze"):
            analyze_run(session, run_id=run_id, router=router, registry=registry)
        with _stage(session, run_id, "map"):
            map_strategy_run(session, run_id=run_id, router=router, registry=registry)
        with _stage(session, run_id, "strategy"):
            run_strategy_stage(session, run_id=run_id, router=router, registry=registry)

        RunRepo(session).finish(run_id)
        session.commit()
        log.info("pipeline_completed", run_id=run_id)
    except Exception as exc:  # noqa: BLE001 — a failed run must be recorded, not propagated
        session.rollback()
        try:
            RunRepo(session).finish(run_id, error=f"{type(exc).__name__}: {exc}")
            session.commit()
        except Exception:  # noqa: BLE001
            session.rollback()
        log.exception("pipeline_failed", run_id=run_id)
    finally:
        session.close()
