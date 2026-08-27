"""Schedule management routes (EPIC-08)."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.deps import get_session
from app.config.settings import get_app_config
from app.core.logging import get_logger
from app.db.repos import ScheduleRepo
from app.scheduler.service import InvalidCronError, validate_cron

log = get_logger(__name__)
router = APIRouter(prefix="/api/schedule", tags=["schedule"])
SessionDep = Annotated[Session, Depends(get_session)]


class ScheduleCreate(BaseModel):
    cron: str = Field(
        default_factory=lambda: get_app_config().loop.get("default_cron", "0 6 * * 1")
    )
    period_days: int = 30
    adapter: str = "mock"
    enabled: bool = True


class ScheduleOut(BaseModel):
    id: int
    cron: str
    period_days: int
    adapter: str
    enabled: bool
    last_run_id: int | None
    next_run_at: str | None


def _scheduler(request: Request):
    return getattr(request.app.state, "scheduler", None)


def _out(row, request: Request) -> ScheduleOut:
    svc = _scheduler(request)
    nxt = svc.next_run_time(row.id) if svc else None
    return ScheduleOut(
        id=row.id,
        cron=row.cron,
        period_days=row.period_days,
        adapter=row.adapter,
        enabled=row.enabled,
        last_run_id=row.last_run_id,
        next_run_at=nxt.isoformat() if nxt else None,
    )


@router.post("", response_model=ScheduleOut, status_code=201)
def create_schedule(body: ScheduleCreate, request: Request, session: SessionDep) -> ScheduleOut:
    try:
        validate_cron(body.cron)
    except InvalidCronError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    row = ScheduleRepo(session).create(
        cron=body.cron,
        period_days=body.period_days,
        adapter=body.adapter,
        enabled=body.enabled,
    )
    session.commit()
    svc = _scheduler(request)
    if svc:
        svc.sync_schedule(row)
    log.info("schedule_created", schedule_id=row.id, cron=row.cron)
    return _out(row, request)


@router.get("", response_model=list[ScheduleOut])
def list_schedules(request: Request, session: SessionDep) -> list[ScheduleOut]:
    return [_out(r, request) for r in ScheduleRepo(session).list_all()]


@router.delete("/{schedule_id}", status_code=204)
def delete_schedule(schedule_id: int, request: Request, session: SessionDep) -> None:
    if not ScheduleRepo(session).delete(schedule_id):
        raise HTTPException(status_code=404, detail=f"No schedule {schedule_id}")
    session.commit()
    svc = _scheduler(request)
    if svc:
        svc.remove_schedule(schedule_id)
