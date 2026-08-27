"""Read-only result sections for a completed run (EPIC-07)."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.deps import get_session
from app.api.results_service import PostQuery, ResultsService

router = APIRouter(prefix="/api/results", tags=["results"])
SessionDep = Annotated[Session, Depends(get_session)]


def _svc(session: Session, run_id: int) -> ResultsService:
    svc = ResultsService(session)
    svc.require_completed_run(run_id)  # raises RunNotFound / RunNotReady -> 404 / 409
    return svc


@router.get("/{run_id}/summary")
def summary(run_id: int, session: SessionDep):
    return _svc(session, run_id).summary(run_id)


@router.get("/{run_id}/posts")
def posts(
    run_id: int,
    session: SessionDep,
    limit: int = Query(50, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    competitor_id: int | None = None,
    format: str | None = None,
    topic: str | None = None,
    sort: str = "engagement_score",
    order: str = Query("desc", pattern="^(asc|desc)$"),
):
    q = PostQuery(
        limit=limit,
        offset=offset,
        competitor_id=competitor_id,
        format=format,
        topic=topic,
        sort=sort,
        order=order,
    )
    return _svc(session, run_id).posts(run_id, q)


@router.get("/{run_id}/formats")
def formats(run_id: int, session: SessionDep):
    return _svc(session, run_id).formats(run_id)


@router.get("/{run_id}/topics")
def topics(run_id: int, session: SessionDep):
    return _svc(session, run_id).topics(run_id)


@router.get("/{run_id}/ctas")
def ctas(run_id: int, session: SessionDep):
    return _svc(session, run_id).ctas(run_id)


@router.get("/{run_id}/keywords")
def keywords(run_id: int, session: SessionDep):
    return _svc(session, run_id).keywords(run_id)


@router.get("/{run_id}/campaigns")
def campaigns(run_id: int, session: SessionDep):
    return _svc(session, run_id).campaigns(run_id)


@router.get("/{run_id}/profiles")
def profiles(run_id: int, session: SessionDep):
    return _svc(session, run_id).profiles(run_id)


@router.get("/{run_id}/cross")
def cross(run_id: int, session: SessionDep):
    return _svc(session, run_id).cross(run_id)


@router.get("/{run_id}/top-content")
def top_content(run_id: int, session: SessionDep):
    return _svc(session, run_id).top_content(run_id)


@router.get("/{run_id}/strategy")
def strategy(run_id: int, session: SessionDep):
    return _svc(session, run_id).strategy(run_id)


@router.get("/{run_id}/opportunities")
def opportunities(run_id: int, session: SessionDep):
    return _svc(session, run_id).opportunities(run_id)


@router.get("/{run_id}/calendar")
def calendar(run_id: int, session: SessionDep):
    return _svc(session, run_id).calendar(run_id)


@router.get("/{run_id}/diff")
def diff(run_id: int, session: SessionDep):
    """Period-over-period diff + change report (EPIC-08); null when the run has none."""
    svc = _svc(session, run_id)
    return {"diff": svc.diff(run_id), "change_report": svc.change_report(run_id)}
