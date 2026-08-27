"""LangGraph analysis stage (EPIC-04): ``score -> rank -> detect_campaigns``.

Appended after the EPIC-03 classification subgraph. ``score`` writes engagement
score/rate onto ``post_intelligence``; ``rank`` materialises the top-N views for the
result bundle (queries are otherwise computed on demand); ``detect_campaigns`` runs the
deep-agent-or-stub campaign pipeline and persists ``campaigns``. Fully offline under
FakeLLM + ``FakeCampaignAgent``.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, TypedDict

from langgraph.graph import END, START, StateGraph
from sqlalchemy.orm import Session

from app.analysis.campaigns import CampaignDetectionResult, detect_campaigns_for_run
from app.analysis.engagement import ScoreRunResult, score_run
from app.config.settings import AppConfig, get_app_config
from app.core.logging import get_logger
from app.core.model_router import ModelRouter
from app.core.prompt_registry import PromptRegistry
from app.db.repos import AnalysisRepo, RunRepo
from app.schemas.analysis import (
    CompetitorTopPosts,
    CtaPerformance,
    FormatPerformance,
    TopicPerformance,
    TopPost,
)

log = get_logger(__name__)


@dataclass
class RankingSnapshot:
    top_posts: list[TopPost]
    top_posts_by_competitor: list[CompetitorTopPosts]
    top_formats: list[FormatPerformance]
    top_topics: list[TopicPerformance]
    top_ctas: list[CtaPerformance]


@dataclass
class AnalysisResult:
    run_id: int
    score: ScoreRunResult
    rankings: RankingSnapshot
    campaigns: CampaignDetectionResult


@dataclass
class AnalysisDeps:
    session: Session
    router: ModelRouter
    registry: PromptRegistry
    app_config: AppConfig
    run_id: int
    top_posts: int
    top_posts_per_competitor: int
    campaign_agent: object | None


class AnalysisState(TypedDict, total=False):
    score: ScoreRunResult
    rankings: RankingSnapshot
    campaigns: CampaignDetectionResult


def build_analysis_graph(deps: AnalysisDeps) -> Any:
    def score_node(state: AnalysisState) -> AnalysisState:
        result = score_run(
            deps.session, run_id=deps.run_id, app_config=deps.app_config, set_stage=True
        )
        return {"score": result}

    def rank_node(state: AnalysisState) -> AnalysisState:
        RunRepo(deps.session).set_stage(deps.run_id, "rank")
        repo = AnalysisRepo(deps.session)
        snapshot = RankingSnapshot(
            top_posts=repo.top_posts(deps.run_id, deps.top_posts),
            top_posts_by_competitor=repo.top_posts_by_competitor(
                deps.run_id, deps.top_posts_per_competitor
            ),
            top_formats=repo.top_formats(deps.run_id),
            top_topics=repo.top_topics(deps.run_id),
            top_ctas=repo.top_ctas(deps.run_id),
        )
        log.info(
            "rankings_built",
            run_id=deps.run_id,
            formats=len(snapshot.top_formats),
            topics=len(snapshot.top_topics),
        )
        return {"rankings": snapshot}

    def detect_campaigns_node(state: AnalysisState) -> AnalysisState:
        result = detect_campaigns_for_run(
            deps.session,
            run_id=deps.run_id,
            router=deps.router,
            registry=deps.registry,
            app_config=deps.app_config,
            agent=deps.campaign_agent,
            set_stage=True,
        )
        return {"campaigns": result}

    graph = StateGraph(AnalysisState)
    graph.add_node("score", score_node)
    graph.add_node("rank", rank_node)
    graph.add_node("detect_campaigns", detect_campaigns_node)
    graph.add_edge(START, "score")
    graph.add_edge("score", "rank")
    graph.add_edge("rank", "detect_campaigns")
    graph.add_edge("detect_campaigns", END)
    return graph.compile()


def analyze_run(
    session: Session,
    *,
    run_id: int,
    router: ModelRouter,
    registry: PromptRegistry,
    app_config: AppConfig | None = None,
    campaign_agent: object | None = None,
) -> AnalysisResult:
    """Run ``score -> rank -> detect_campaigns`` for a classified run."""
    app_config = app_config or get_app_config()
    analysis_cfg = app_config.analysis or {}
    deps = AnalysisDeps(
        session=session,
        router=router,
        registry=registry,
        app_config=app_config,
        run_id=run_id,
        top_posts=int(analysis_cfg.get("top_posts", 20)),
        top_posts_per_competitor=int(analysis_cfg.get("top_posts_per_competitor", 5)),
        campaign_agent=campaign_agent,
    )
    final: AnalysisState = build_analysis_graph(deps).invoke({})
    return AnalysisResult(
        run_id=run_id,
        score=final["score"],
        rankings=final["rankings"],
        campaigns=final["campaigns"],
    )
