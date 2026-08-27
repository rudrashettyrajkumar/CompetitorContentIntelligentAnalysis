"""RFC 7807 problem responses for the API (EPIC-07)."""

from __future__ import annotations

from fastapi import Request
from fastapi.responses import JSONResponse

from app.api.results_service import RunNotFound, RunNotReady


def problem(status: int, title: str, detail: str, *, type_: str = "about:blank") -> JSONResponse:
    return JSONResponse(
        status_code=status,
        content={"type": type_, "title": title, "status": status, "detail": detail},
        media_type="application/problem+json",
    )


def install_error_handlers(app) -> None:
    @app.exception_handler(RunNotFound)
    async def _not_found(_request: Request, exc: RunNotFound) -> JSONResponse:
        return problem(
            404, "Run not found", f"No run with id {exc}", type_="urn:problem:run-not-found"
        )

    @app.exception_handler(RunNotReady)
    async def _not_ready(_request: Request, exc: RunNotReady) -> JSONResponse:
        return problem(
            409,
            "Run still processing",
            f"Run status is {exc.status!r}; results are available once it is 'completed'.",
            type_="urn:problem:run-not-ready",
        )
