"""SchedulerService: cron validation, overlap guard, and a real APScheduler trigger."""

import asyncio

import pytest

from app.db.engine import build_engine, build_session_factory, init_db
from app.db.repos import CompetitorRepo, RunRepo, ScheduleRepo
from app.scheduler.service import InvalidCronError, SchedulerService, make_trigger, validate_cron
from app.schemas.collection import CompanyProfile


@pytest.fixture
def factory(tmp_path):
    engine = build_engine(f"sqlite:///{tmp_path}/sched.db")
    init_db(engine)
    f = build_session_factory(engine)
    yield f
    engine.dispose()


def _add_competitor(factory):
    s = factory()
    c = CompetitorRepo(s).upsert(name="Acme", linkedin_url="https://www.linkedin.com/company/acme")
    from app.db.repos import ProfileRepo

    ProfileRepo(s).upsert(c.id, CompanyProfile(followers=10_000))
    s.commit()
    s.close()


def test_cron_validation():
    validate_cron("0 6 * * 1")
    validate_cron("@every 5s")
    with pytest.raises(InvalidCronError):
        validate_cron("not a cron")
    with pytest.raises(InvalidCronError):
        validate_cron("99 99 * * *")
    with pytest.raises(InvalidCronError):
        make_trigger("@every -2s")


def test_overlap_guard_skips_when_a_run_is_in_progress(factory, monkeypatch):
    monkeypatch.setenv("LLM_FAKE_MODE", "true")
    _add_competitor(factory)
    s = factory()
    ScheduleRepo(s).create(cron="@every 1s", period_days=30, adapter="mock")
    RunRepo(s).create(period_days=30, adapter="mock")  # status 'pending' == in progress
    s.commit()
    sched_id = ScheduleRepo(s).list_all()[0].id
    runs_before = len(RunRepo(s).list_all())
    s.close()

    svc = SchedulerService(factory)
    started = svc._start_scheduled_run(sched_id)
    assert started is None  # overlap guard fired

    s = factory()
    assert len(RunRepo(s).list_all()) == runs_before  # no new run created
    s.close()


async def test_apscheduler_fires_a_real_scheduled_run(factory, monkeypatch):
    monkeypatch.setenv("LLM_FAKE_MODE", "true")
    from app.config.settings import get_settings

    get_settings.cache_clear()
    _add_competitor(factory)

    s = factory()
    ScheduleRepo(s).create(cron="@every 1s", period_days=30, adapter="mock", enabled=True)
    s.commit()
    s.close()

    svc = SchedulerService(factory)
    svc.start()
    try:
        for _ in range(120):  # up to ~12s
            await asyncio.sleep(0.1)
            s = factory()
            runs = RunRepo(s).list_all()
            done = [r for r in runs if r.trigger == "scheduled" and r.status == "completed"]
            s.close()
            if done:
                break
        assert done, "no scheduled run completed via APScheduler"
        assert done[0].trigger == "scheduled"
        assert set(done[0].stage_timings) >= {"collect", "classify", "analyze"}
    finally:
        svc.shutdown(wait=False)
        get_settings.cache_clear()
