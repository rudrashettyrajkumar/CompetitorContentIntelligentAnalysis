"""Competitor CRUD + Excel upload (EPIC-02 surface, moved under routers/ in EPIC-07)."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, UploadFile
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.api.deps import get_session
from app.core.logging import get_logger
from app.db.repos import CompetitorRepo
from app.input.excel import IngestError, ingest_excel

log = get_logger(__name__)
router = APIRouter(prefix="/api/competitors", tags=["competitors"])
SessionDep = Annotated[Session, Depends(get_session)]


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


@router.post("/upload", response_model=UploadResponse)
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


def _out(c) -> CompetitorOut:
    return CompetitorOut(
        id=c.id,
        name=c.name,
        linkedin_url=c.linkedin_url,
        industry=c.industry,
        market=c.market,
        priority=c.priority,
        status=c.status,
    )


@router.get("", response_model=list[CompetitorOut])
def list_competitors(session: SessionDep) -> list[CompetitorOut]:
    return [_out(c) for c in CompetitorRepo(session).list_all(status=None)]


@router.get("/{competitor_id}", response_model=CompetitorOut)
def get_competitor(competitor_id: int, session: SessionDep) -> CompetitorOut:
    c = CompetitorRepo(session).get(competitor_id)
    if c is None:
        raise HTTPException(status_code=404, detail=f"No competitor {competitor_id}")
    return _out(c)


@router.delete("/{competitor_id}", status_code=204)
def delete_competitor(competitor_id: int, session: SessionDep) -> None:
    if not CompetitorRepo(session).delete(competitor_id):
        raise HTTPException(status_code=404, detail=f"No competitor {competitor_id}")
