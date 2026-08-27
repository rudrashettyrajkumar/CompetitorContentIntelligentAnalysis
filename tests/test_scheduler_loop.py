"""run_loop_step: persistence, change report, and the auto strategy-refresh path (EPIC-08)."""

import pytest

from app.core.model_router import ModelRouter
from app.db.repos import InsightRepo, RunRepo
from app.scheduler.fakes import register_loop_fakes
from app.scheduler.loop import run_loop_step
from app.scheduler.notifier import Notifier
from app.strategy.fakes import register_strategy_fakes
from test_scheduler_diff import _BASELINE, _CURRENT, _seed_run


class _RecordingNotifier(Notifier):
    def __init__(self):
        self.calls = []

    def notify(self, *, diff, report):
        self.calls.append((diff, report))


@pytest.fixture
def loop_router(settings, models_config, fake_llm):
    register_strategy_fakes(fake_llm)
    register_loop_fakes(fake_llm)
    return ModelRouter(settings, models_config, fake_llm=fake_llm, backoff_base=0)


def _material_pair(session):
    base = _seed_run(
        session,
        tag="lb",
        rows=_BASELINE,
        campaigns={"Cloud push": [6, 7, 8]},
        profile={"cadence": 2.0, "best_format": "text_only", "mix": {"text": 60.0}},
    )
    cur = _seed_run(
        session,
        tag="lc",
        rows=_CURRENT,
        campaigns={"Cloud push": [6, 7, 8], "AI blitz": [0, 1, 2]},
        profile={"cadence": 5.0, "best_format": "carousel", "mix": {"visual": 60.0}},
    )
    RunRepo(session).finish(base)
    session.commit()
    return base, cur


def test_loop_step_no_baseline_is_noop(db_session, loop_router, prompt_registry):
    run = _seed_run(
        db_session,
        tag="solo",
        rows=_BASELINE,
        campaigns={},
        profile={"cadence": 2.0, "best_format": "text_only", "mix": {"text": 60.0}},
    )
    result = run_loop_step(db_session, run_id=run, router=loop_router, registry=prompt_registry)
    assert result.diff is None and result.report is None


def test_loop_step_persists_diff_and_report_and_refreshes(db_session, loop_router, prompt_registry):
    base, cur = _material_pair(db_session)
    notifier = _RecordingNotifier()

    result = run_loop_step(
        db_session, run_id=cur, router=loop_router, registry=prompt_registry, notifier=notifier
    )

    assert result.diff is not None
    assert result.diff.strategy_refresh_recommended is True
    assert result.strategy_refreshed is True
    assert notifier.calls and notifier.calls[0][0].current_run_id == cur

    repo = InsightRepo(db_session)
    pd = repo.get_payload(cur, "period_diff")
    cr = repo.get_payload(cur, "change_report")
    assert pd and pd["new_campaigns"] == ["AI blitz"]
    assert cr and cr["narrative"] and cr["strategy_refreshed"] is True
    # refresh actually (re)wrote the strategy bundle for this run
    assert repo.get_payload(cur, "strategy") is not None
    assert repo.get_payload(cur, "calendar") is not None


def test_quiet_diff_does_not_refresh_strategy(db_session, loop_router, prompt_registry):
    a = _seed_run(
        db_session,
        tag="qa",
        rows=_BASELINE,
        campaigns={"Cloud push": [6, 7, 8]},
        profile={"cadence": 2.0, "best_format": "text_only", "mix": {"text": 60.0}},
    )
    RunRepo(db_session).finish(a)
    b = _seed_run(
        db_session,
        tag="qb",
        rows=_BASELINE,
        campaigns={"Cloud push": [6, 7, 8]},
        profile={"cadence": 2.0, "best_format": "text_only", "mix": {"text": 60.0}},
    )
    db_session.commit()

    result = run_loop_step(db_session, run_id=b, router=loop_router, registry=prompt_registry)
    assert result.diff is not None
    assert result.strategy_refreshed is False
    cr = InsightRepo(db_session).get_payload(b, "change_report")
    assert cr["strategy_refreshed"] is False
