"""Engine/session factory. DATABASE_URL is the single switch (SQLite -> Postgres)."""

from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from app.db.models import Base


def _normalize_pg_url(url: str) -> str:
    """Pin psycopg2 and accept the ``postgres://`` scheme managed hosts (Render,
    Heroku, Supabase) hand out but SQLAlchemy 2.0 rejects."""
    if url.startswith("postgres://"):
        url = "postgresql://" + url[len("postgres://") :]
    if url.startswith("postgresql://"):
        url = "postgresql+psycopg2://" + url[len("postgresql://") :]
    return url


def build_engine(database_url: str) -> Engine:
    if database_url.startswith("sqlite:///"):
        db_path = Path(database_url.removeprefix("sqlite:///"))
        if db_path.parent != Path("."):
            db_path.parent.mkdir(parents=True, exist_ok=True)
        return create_engine(database_url, connect_args={"check_same_thread": False})
    # Managed Postgres: pre-ping and recycle so a paused/reaped pooler connection
    # (Render free tier, Supabase/Neon autosuspend) doesn't surface as a 500.
    return create_engine(_normalize_pg_url(database_url), pool_pre_ping=True, pool_recycle=300)


def build_session_factory(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(bind=engine, expire_on_commit=False)


def init_db(engine: Engine) -> None:
    Base.metadata.create_all(engine)
