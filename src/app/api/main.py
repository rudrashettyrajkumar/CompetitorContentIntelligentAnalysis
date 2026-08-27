"""FastAPI application factory. Routers are added by later epics."""

from contextlib import asynccontextmanager

from fastapi import FastAPI

from app import __version__
from app.config.settings import get_settings
from app.core.logging import configure_logging, get_logger
from app.db.engine import build_engine, build_session_factory, init_db

log = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    configure_logging(settings.log_level)
    engine = build_engine(settings.database_url)
    init_db(engine)
    app.state.engine = engine
    app.state.session_factory = build_session_factory(engine)
    log.info("app_started", database=settings.database_url, fake_llm=settings.llm_fake_mode)
    yield
    engine.dispose()


def create_app() -> FastAPI:
    app = FastAPI(title="Competitor & Content Intelligence", version=__version__, lifespan=lifespan)

    @app.get("/api/health")
    def health() -> dict:
        return {"status": "ok", "version": __version__}

    return app


app = create_app()
