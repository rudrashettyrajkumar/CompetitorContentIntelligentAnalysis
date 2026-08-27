"""Loop step run after a completed run (EPIC-08): diff → change report → notify → refresh.

Called from the pipeline (for scheduled runs, or any run that has a prior completed run)
and available standalone. Persists ``insights.kind = period_diff`` and
``insights.kind = change_report``; when the diff recommends it, re-runs the EPIC-06
strategy stage for the current run and records the pre-refresh pillars for comparison.
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.config.settings import AppConfig, get_app_config
from app.core.logging import get_logger
from app.core.model_router import ModelRouter
from app.core.prompt_registry import PromptRegistry
from app.db.repos import InsightRepo
from app.scheduler.change_report import generate_change_report
from app.scheduler.diff import diff_against_previous
from app.scheduler.notifier import LogNotifier, Notifier
from app.schemas.loop import ChangeReport, PeriodDiff

log = get_logger(__name__)


@dataclass
class LoopResult:
    run_id: int
    diff: PeriodDiff | None
    report: ChangeReport | None
    strategy_refreshed: bool


def run_loop_step(
    session: Session,
    *,
    run_id: int,
    router: ModelRouter,
    registry: PromptRegistry,
    app_config: AppConfig | None = None,
    notifier: Notifier | None = None,
) -> LoopResult:
    app_config = app_config or get_app_config()
    notifier = notifier or LogNotifier()
    insight_repo = InsightRepo(session)

    result = diff_against_previous(session, run_id=run_id, app_config=app_config)
    if result.diff is None:
        return LoopResult(run_id=run_id, diff=None, report=None, strategy_refreshed=False)

    diff = result.diff
    insight_repo.put(run_id, "period_diff", diff.model_dump(mode="json"))
    session.commit()

    report = generate_change_report(diff, router=router, registry=registry)

    strategy_refreshed = False
    previous_pillars: list[str] = []
    if diff.strategy_refresh_recommended:
        prev = insight_repo.get_payload(run_id, "strategy") or {}
        previous_pillars = [p.get("name", "") for p in prev.get("pillars", [])]
        from app.strategy.graph import run_strategy_stage

        run_strategy_stage(session, run_id=run_id, router=router, registry=registry)
        session.commit()
        strategy_refreshed = True
        log.info("strategy_refreshed_by_loop", run_id=run_id, reasons=diff.refresh_reasons)

    insight_repo.put(
        run_id,
        "change_report",
        {
            **report.model_dump(mode="json"),
            "strategy_refreshed": strategy_refreshed,
            "previous_pillars": previous_pillars,
            "baseline_run_id": diff.baseline_run_id,
        },
    )
    session.commit()

    notifier.notify(diff=diff, report=report)
    return LoopResult(
        run_id=run_id, diff=diff, report=report, strategy_refreshed=strategy_refreshed
    )
