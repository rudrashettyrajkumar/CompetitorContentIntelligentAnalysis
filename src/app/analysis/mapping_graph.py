"""LangGraph mapping stage (EPIC-05): ``profiles -> cross -> top_content``.

Runs after the EPIC-04 analysis stage. ``profiles`` builds and persists a
:class:`StrategyProfile` per competitor; ``cross`` computes cross-competitor insights;
``top_content`` ranks the Top-N posts and attaches a ``WhyItWorked`` breakdown. The cross
and top-content bundles are persisted to ``insights`` (kinds ``cross_competitor`` and
``top_content``). Fully offline under FakeLLM + the mapping fakes.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, TypedDict

from langgraph.graph import END, START, StateGraph
from sqlalchemy.orm import Session

from app.analysis.cross import CrossRunResult, build_cross_insights
from app.analysis.strategy_profile import ProfileRunResult, build_strategy_profiles
from app.analysis.top_content import TopContentRunResult, build_top_content
from app.config.settings import AppConfig, get_app_config
from app.core.logging import get_logger
from app.core.model_router import ModelRouter
from app.core.prompt_registry import PromptRegistry
from app.db.repos import InsightRepo, StrategyProfileRepo

log = get_logger(__name__)


@dataclass
class MappingResult:
    run_id: int
    profiles: ProfileRunResult
    cross: CrossRunResult
    top_content: TopContentRunResult


@dataclass
class MappingDeps:
    session: Session
    router: ModelRouter
    registry: PromptRegistry
    app_config: AppConfig
    run_id: int


class MappingState(TypedDict, total=False):
    profiles: ProfileRunResult
    cross: CrossRunResult
    top_content: TopContentRunResult


def build_mapping_graph(deps: MappingDeps) -> Any:
    def profiles_node(state: MappingState) -> MappingState:
        result = build_strategy_profiles(
            deps.session,
            run_id=deps.run_id,
            router=deps.router,
            registry=deps.registry,
            app_config=deps.app_config,
            set_stage=True,
        )
        StrategyProfileRepo(deps.session).replace_for_run(deps.run_id, result.profiles)
        deps.session.commit()
        return {"profiles": result}

    def cross_node(state: MappingState) -> MappingState:
        result = build_cross_insights(
            deps.session,
            run_id=deps.run_id,
            app_config=deps.app_config,
            set_stage=True,
        )
        InsightRepo(deps.session).put(
            deps.run_id, "cross_competitor", result.insights.model_dump(mode="json")
        )
        deps.session.commit()
        return {"cross": result}

    def top_content_node(state: MappingState) -> MappingState:
        result = build_top_content(
            deps.session,
            run_id=deps.run_id,
            router=deps.router,
            registry=deps.registry,
            app_config=deps.app_config,
            set_stage=True,
        )
        InsightRepo(deps.session).put(
            deps.run_id, "top_content", result.report.model_dump(mode="json")
        )
        deps.session.commit()
        return {"top_content": result}

    graph = StateGraph(MappingState)
    graph.add_node("profiles", profiles_node)
    graph.add_node("cross", cross_node)
    graph.add_node("top_content", top_content_node)
    graph.add_edge(START, "profiles")
    graph.add_edge("profiles", "cross")
    graph.add_edge("cross", "top_content")
    graph.add_edge("top_content", END)
    return graph.compile()


def map_strategy_run(
    session: Session,
    *,
    run_id: int,
    router: ModelRouter,
    registry: PromptRegistry,
    app_config: AppConfig | None = None,
) -> MappingResult:
    """Run ``profiles -> cross -> top_content`` for an analysed run."""
    app_config = app_config or get_app_config()
    deps = MappingDeps(
        session=session,
        router=router,
        registry=registry,
        app_config=app_config,
        run_id=run_id,
    )
    final: MappingState = build_mapping_graph(deps).invoke({})
    return MappingResult(
        run_id=run_id,
        profiles=final["profiles"],
        cross=final["cross"],
        top_content=final["top_content"],
    )
