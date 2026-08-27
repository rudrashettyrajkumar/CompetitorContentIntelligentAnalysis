"""Run lifecycle: start the pipeline in the background, poll status + stage progress."""

from __future__ import annotations

from typing import Annotated

import anyio
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.deps import get_session
from app.config.settings import get_app_config, get_settings
from app.core.logging import get_logger
from app.datasources.base import get_datasource, resolve_period_days
from app.db.repos import CompetitorRepo, RunRepo
from app.pipeline import run_pipeline

log = get_logger(__name__)
router = APIRouter(prefix="/api/runs", tags=["runs"])
SessionDep = Annotated[Session, Depends(get_session)]

_PIPELINE_STAGES = ["collect", "classify", "analyze", "map", "strategy", "loop"]


class RunCreate(BaseModel):
    period_days: int | None = Field(default=None, description="7 | 10 | 30 | 60 | 90")
    adapter: str | None = None
    competitor_ids: list[int] | None = None


class RunOut(BaseModel):
    id: int
    status: str
    stage: str | None
    adapter: str
    period_days: int
    trigger: str
    started_at: str | None
    finished_at: str | None
    error: str | None
    stage_timings: dict[str, float]
    stages: list[str]


def _out(run) -> RunOut:
    return RunOut(
        id=run.id,
        status=run.status,
        stage=run.stage,
        adapter=run.adapter,
        period_days=run.period_days,
        trigger=run.trigger,
        started_at=run.started_at.isoformat() if run.started_at else None,
        finished_at=run.finished_at.isoformat() if run.finished_at else None,
        error=run.error,
        stage_timings=run.stage_timings or {},
        stages=_PIPELINE_STAGES,
    )


async def _run_in_thread(session_factory, run_id: int) -> None:
    await anyio.to_thread.run_sync(run_pipeline, session_factory, run_id)


@router.post("", response_model=RunOut, status_code=202)
def create_run(
    body: RunCreate, request: Request, session: SessionDep, background: BackgroundTasks
) -> RunOut:
    settings = get_settings()
    app_config = get_app_config()

    try:
        period_days = resolve_period_days(body.period_days, app_config)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    adapter_name = (body.adapter or app_config.collection.get("adapter", "mock")).lower()
    try:
        get_datasource(adapter_name, settings, app_config)
    except (ValueError, RuntimeError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    competitor_repo = CompetitorRepo(session)
    if body.competitor_ids:
        competitors = [
            c for cid in body.competitor_ids if (c := competitor_repo.get(cid)) is not None
        ]
    else:
        competitors = competitor_repo.list_all(status="active")
    if not competitors:
        raise HTTPException(status_code=400, detail="No competitors to analyse")

    run = RunRepo(session).create(
        period_days=period_days,
        adapter=adapter_name,
        trigger="manual",
        competitor_ids=body.competitor_ids or None,
    )
    session.commit()

    background.add_task(_run_in_thread, request.app.state.session_factory, run.id)
    log.info("run_started", run_id=run.id, adapter=adapter_name, period_days=period_days)
    return _out(RunRepo(session).get(run.id))


@router.get("", response_model=list[RunOut])
def list_runs(session: SessionDep) -> list[RunOut]:
    return [_out(r) for r in RunRepo(session).list_all()]


@router.get("/{run_id}", response_model=RunOut)
def get_run(run_id: int, session: SessionDep, response: Response) -> RunOut:
    run = RunRepo(session).get(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail=f"No run {run_id}")
    if run.status in ("pending", "running"):
        response.headers["Retry-After"] = "2"
    return _out(run)
