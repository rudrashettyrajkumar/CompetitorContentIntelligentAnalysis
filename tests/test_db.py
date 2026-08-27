from sqlalchemy import inspect

from app.db.engine import build_engine, init_db
from app.db.repos import CompetitorRepo, RunRepo

EXPECTED_TABLES = {
    "competitors",
    "company_profiles",
    "posts",
    "post_intelligence",
    "campaigns",
    "runs",
    "strategy_profiles",
    "insights",
}


def test_init_db_creates_all_tables(tmp_path):
    engine = build_engine(f"sqlite:///{tmp_path}/test.db")
    init_db(engine)
    assert EXPECTED_TABLES <= set(inspect(engine).get_table_names())
    engine.dispose()


def test_competitor_upsert_roundtrip(db_session):
    repo = CompetitorRepo(db_session)
    created = repo.upsert(
        name="Acme IT",
        linkedin_url="https://www.linkedin.com/company/acme-it",
        industry="IT Services",
        market="USA",
        priority="High",
    )
    assert created.id is not None

    updated = repo.upsert(
        name="Acme IT Services",
        linkedin_url="https://www.linkedin.com/company/acme-it",
        priority="Medium",
    )
    assert updated.id == created.id
    assert updated.name == "Acme IT Services"
    assert len(repo.list_all()) == 1


def test_competitor_delete(db_session):
    repo = CompetitorRepo(db_session)
    c = repo.upsert(name="X", linkedin_url="https://www.linkedin.com/company/x")
    assert repo.delete(c.id) is True
    assert repo.delete(9999) is False
    assert repo.list_all() == []


def test_run_lifecycle(db_session):
    repo = RunRepo(db_session)
    run = repo.create(period_days=30, adapter="mock")
    assert run.status == "pending"

    repo.set_stage(run.id, "collect")
    assert repo.get(run.id).status == "running"
    assert repo.get(run.id).stage == "collect"

    repo.finish(run.id)
    finished = repo.get(run.id)
    assert finished.status == "completed"
    assert finished.finished_at is not None


def test_run_finish_with_error(db_session):
    repo = RunRepo(db_session)
    run = repo.create(period_days=7, adapter="mock")
    repo.finish(run.id, error="boom")
    assert repo.get(run.id).status == "failed"
    assert repo.get(run.id).error == "boom"
