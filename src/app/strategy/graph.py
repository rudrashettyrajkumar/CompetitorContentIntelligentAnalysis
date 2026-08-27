"""LangGraph strategy stage (EPIC-06): ``strategy -> opportunities -> calendar``.

Runs after the EPIC-05 mapping stage. Each node sets ``run.stage``, runs its step from
``strategy/generator.py``, and persists its output to ``insights``:

* ``strategy``      -> ``insights.kind = strategy``      (ContentStrategy)
* ``opportunities`` -> ``insights.kind = opportunities`` ({opportunities, originality_checks})
* ``calendar``      -> ``insights.kind = calendar``      ({calendar, valid, errors})

Fully offline under FakeLLM + FakeStrategyAgent + the strategy fakes.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, TypedDict

from langgraph.graph import END, START, StateGraph
from sqlalchemy.orm import Session

from app.config.settings import AppConfig, get_app_config
from app.core.logging import get_logger
from app.core.model_router import ModelRouter
from app.core.prompt_registry import PromptRegistry
from app.db.repos import InsightRepo, RunRepo
from app.schemas.strategy import (
    ContentCalendar,
    ContentOpportunity,
    ContentStrategy,
    StrategyBundle,
)
from app.strategy.calendar_check import CalendarValidation
from app.strategy.generator import (
    StrategyConfig,
    resolve_agent,
    step_calendar,
    step_opportunities,
    step_pillars,
)
from app.strategy.inputs import assemble_strategy_inputs

log = get_logger(__name__)


@dataclass
class StrategyStageResult:
    run_id: int
    bundle: StrategyBundle
    calendar_valid: bool
    calendar_errors: list[str]


@dataclass
class StrategyDeps:
    session: Session
    router: ModelRouter
    registry: PromptRegistry
    cfg: StrategyConfig
    run_id: int
    agent: Any


class StrategyState(TypedDict, total=False):
    inputs: Any
    strategy: ContentStrategy
    opportunities: list[ContentOpportunity]
    checks: list
    calendar: ContentCalendar
    validation: CalendarValidation


def build_strategy_graph(deps: StrategyDeps) -> Any:
    def strategy_node(state: StrategyState) -> StrategyState:
        RunRepo(deps.session).set_stage(deps.run_id, "strategy")
        inputs = assemble_strategy_inputs(deps.session, run_id=deps.run_id)
        strategy = step_pillars(inputs, deps.agent, deps.cfg)
        InsightRepo(deps.session).put(deps.run_id, "strategy", strategy.model_dump(mode="json"))
        deps.session.commit()
        return {"inputs": inputs, "strategy": strategy}

    def opportunities_node(state: StrategyState) -> StrategyState:
        RunRepo(deps.session).set_stage(deps.run_id, "opportunities")
        opportunities, checks = step_opportunities(
            state["inputs"],
            deps.agent,
            state["strategy"],
            router=deps.router,
            registry=deps.registry,
            cfg=deps.cfg,
        )
        InsightRepo(deps.session).put(
            deps.run_id,
            "opportunities",
            {
                "opportunities": [o.model_dump(mode="json") for o in opportunities],
                "originality_checks": [c.model_dump(mode="json") for c in checks],
            },
        )
        deps.session.commit()
        return {"opportunities": opportunities, "checks": checks}

    def calendar_node(state: StrategyState) -> StrategyState:
        RunRepo(deps.session).set_stage(deps.run_id, "calendar")
        calendar, validation = step_calendar(
            state["inputs"],
            deps.agent,
            state["strategy"],
            state["opportunities"],
            deps.cfg,
        )
        InsightRepo(deps.session).put(
            deps.run_id,
            "calendar",
            {
                "calendar": calendar.model_dump(mode="json"),
                "valid": validation.ok,
                "errors": validation.errors,
            },
        )
        deps.session.commit()
        if not validation.ok:
            log.warning("calendar_validation_failed", run_id=deps.run_id, errors=validation.errors)
        return {"calendar": calendar, "validation": validation}

    graph = StateGraph(StrategyState)
    graph.add_node("strategy", strategy_node)
    graph.add_node("opportunities", opportunities_node)
    graph.add_node("calendar", calendar_node)
    graph.add_edge(START, "strategy")
    graph.add_edge("strategy", "opportunities")
    graph.add_edge("opportunities", "calendar")
    graph.add_edge("calendar", END)
    return graph.compile()


def run_strategy_stage(
    session: Session,
    *,
    run_id: int,
    router: ModelRouter,
    registry: PromptRegistry,
    app_config: AppConfig | None = None,
    agent: object | None = None,
) -> StrategyStageResult:
    """Run ``strategy -> opportunities -> calendar`` for a mapped run, persisting each."""
    app_config = app_config or get_app_config()
    deps = StrategyDeps(
        session=session,
        router=router,
        registry=registry,
        cfg=StrategyConfig.from_app(app_config),
        run_id=run_id,
        agent=resolve_agent(router, registry, agent),
    )
    final: StrategyState = build_strategy_graph(deps).invoke({})
    bundle = StrategyBundle(
        strategy=final["strategy"],
        opportunities=final["opportunities"],
        calendar=final["calendar"],
        originality_checks=final["checks"],
    )
    return StrategyStageResult(
        run_id=run_id,
        bundle=bundle,
        calendar_valid=final["validation"].ok,
        calendar_errors=final["validation"].errors,
    )
