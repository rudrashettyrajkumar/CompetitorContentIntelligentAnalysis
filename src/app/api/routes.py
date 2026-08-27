"""EPIC-02 API surface: competitor upload/list + collect-only runs.

Later epics extend ``POST /api/runs`` into the full pipeline and add the
``/api/results/*`` and ``/api/exports/*`` routes.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.deps import get_session
from app.config.settings import get_app_config, get_settings
from app.core.logging import get_logger
from app.datasources.base import get_datasource, resolve_period_days
from app.datasources.collector import collect_for_run
from app.db.repos import CompetitorRepo, RunRepo
from app.input.excel import IngestError, ingest_excel

log = get_logger(__name__)
router = APIRouter(prefix="/api")
SessionDep = Annotated[Session, Depends(get_session)]


# --------------------------------------------------------------------------- #
# schemas
# --------------------------------------------------------------------------- #
class RowErrorOut(BaseModel):
    row: int
    reason: str


class UploadResponse(BaseModel):
    accepted: int
    rejected: list[RowErrorOut]
    warnings: list[str]
    stored_competitor_ids: list[int]


class CompetitorOut(BaseModel):
    id: int
    name: str
    linkedin_url: str
    industry: str | None
    market: str | None
    priority: str
    status: str


class RunCreate(BaseModel):
    period_days: int | None = Field(default=None, description="7 | 10 | 30 | 60 | 90")
    adapter: str | None = None
    competitor_ids: list[int] | None = None


class CompetitorRunOut(BaseModel):
    competitor_id: int
    name: str
    ok: bool
    posts_seen: int
    posts_inserted: int
    error: str | None


class RunOut(BaseModel):
    run_id: int
    status: str
    adapter: str
    period_days: int
    profiles_collected: int
    posts_inserted: int
    competitors: list[CompetitorRunOut]


# --------------------------------------------------------------------------- #
# routes
# --------------------------------------------------------------------------- #
@router.post("/competitors/upload", response_model=UploadResponse)
async def upload_competitors(file: UploadFile, session: SessionDep) -> UploadResponse:
    payload = await file.read()
    try:
        report = ingest_excel(payload)
    except IngestError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    repo = CompetitorRepo(session)
    stored_ids: list[int] = []
    for competitor in report.accepted:
        row = repo.upsert(
            name=competitor.name,
            linkedin_url=competitor.linkedin_url,
            industry=competitor.industry,
            market=competitor.market,
            priority=competitor.priority,
        )
        stored_ids.append(row.id)

    log.info(
        "competitors_uploaded",
        accepted=report.accepted_count,
        rejected=report.rejected_count,
        filename=file.filename,
    )
    return UploadResponse(
        accepted=report.accepted_count,
        rejected=[RowErrorOut(row=e.row, reason=e.reason) for e in report.rejected],
        warnings=report.warnings,
        stored_competitor_ids=stored_ids,
    )


@router.get("/competitors", response_model=list[CompetitorOut])
def list_competitors(session: SessionDep) -> list[CompetitorOut]:
    return [
        CompetitorOut(
            id=c.id,
            name=c.name,
            linkedin_url=c.linkedin_url,
            industry=c.industry,
            market=c.market,
            priority=c.priority,
            status=c.status,
        )
        for c in CompetitorRepo(session).list_all(status=None)
    ]


@router.post("/runs", response_model=RunOut)
def create_run(body: RunCreate, session: SessionDep) -> RunOut:
    settings = get_settings()
    app_config = get_app_config()

    try:
        period_days = resolve_period_days(body.period_days, app_config)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    adapter_name = (body.adapter or app_config.collection.get("adapter", "mock")).lower()
    try:
        adapter = get_datasource(adapter_name, settings, app_config)
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
        raise HTTPException(status_code=400, detail="No competitors to collect for")

    run_repo = RunRepo(session)
    run = run_repo.create(period_days=period_days, adapter=adapter_name)

    try:
        result = collect_for_run(
            session,
            run_id=run.id,
            competitors=competitors,
            adapter=adapter,
            period_days=period_days,
        )
    except Exception as exc:  # noqa: BLE001 — surface as a failed run, not a 500
        run_repo.finish(run.id, error=f"{type(exc).__name__}: {exc}")
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    run_repo.finish(run.id)
    return RunOut(
        run_id=run.id,
        status=run_repo.get(run.id).status,
        adapter=adapter_name,
        period_days=period_days,
        profiles_collected=result.profiles_collected,
        posts_inserted=result.posts_inserted,
        competitors=[
            CompetitorRunOut(
                competitor_id=r.competitor_id,
                name=r.name,
                ok=r.ok,
                posts_seen=r.posts_seen,
                posts_inserted=r.posts_inserted,
                error=r.error,
            )
            for r in result.per_competitor
        ],
    )
