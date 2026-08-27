"""FastAPI application factory (EPIC-07): full API surface + React SPA static serving."""

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app import __version__
from app.api.errors import install_error_handlers
from app.config.settings import PROJECT_ROOT, get_settings
from app.core.logging import configure_logging, get_logger
from app.db.engine import build_engine, build_session_factory, init_db

log = get_logger(__name__)

FRONTEND_DIST = PROJECT_ROOT / "frontend" / "dist"


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    configure_logging(settings.log_level)
    engine = build_engine(settings.database_url)
    init_db(engine)
    app.state.engine = engine
    app.state.session_factory = build_session_factory(engine)
    app.state.scheduler = None  # populated by EPIC-08 if scheduling is enabled
    log.info("app_started", database=settings.database_url, fake_llm=settings.llm_fake_mode)
    try:
        yield
    finally:
        scheduler = getattr(app.state, "scheduler", None)
        if scheduler is not None:
            scheduler.shutdown(wait=False)
        engine.dispose()


def create_app() -> FastAPI:
    app = FastAPI(title="Competitor & Content Intelligence", version=__version__, lifespan=lifespan)

    @app.get("/api/health", tags=["meta"])
    def health() -> dict:
        return {"status": "ok", "version": __version__}

    from app.api.routers import competitors, exports, results, runs

    for module in (competitors, runs, results, exports):
        app.include_router(module.router)

    try:  # EPIC-08 adds the schedule router; tolerate its absence
        from app.api.routers import schedule

        app.include_router(schedule.router)
    except ImportError:  # pragma: no cover
        pass

    install_error_handlers(app)
    _mount_frontend(app)
    return app


def _mount_frontend(app: FastAPI) -> None:
    """Serve the built SPA at / with a history-API fallback. No-op if not built."""
    dist = FRONTEND_DIST
    if not dist.exists():  # dev: frontend runs on Vite with a proxy to :8000
        return
    assets = dist / "assets"
    if assets.exists():
        app.mount("/assets", StaticFiles(directory=assets), name="assets")

    index = dist / "index.html"

    @app.get("/", include_in_schema=False)
    def _index() -> FileResponse:
        return FileResponse(index)

    @app.get("/{full_path:path}", include_in_schema=False)
    def _spa_fallback(full_path: str) -> FileResponse:
        if full_path.startswith("api/"):
            raise HTTPException(status_code=404, detail="Not found")
        candidate = dist / full_path
        if candidate.is_file():
            return FileResponse(candidate)
        return FileResponse(index)  # client-side routing owns everything else


app = create_app()


# re-exported for any legacy import site
__all__ = ["app", "create_app", "Path"]
