"""Engagement scoring (brief step 4).

``engagement_score = w_r*reactions + w_c*comments + w_s*reposts`` with weights from
``app.yaml: engagement.weights`` (default 1 / 2 / 3). A missing metric counts as 0 but the
row is flagged ``metrics_complete = False``. ``engagement_rate = score / followers * 100``
only when the competitor's follower count is known and positive — otherwise NULL, never a
divide-by-zero.

Scores/rates are written back onto ``post_intelligence`` (``AnalysisRepo.set_post_scores``).
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.config.settings import AppConfig, get_app_config
from app.core.logging import get_logger
from app.db.repos import AnalysisRepo, RunRepo

log = get_logger(__name__)

_DEFAULT_WEIGHTS = {"reactions": 1.0, "comments": 2.0, "reposts": 3.0}


@dataclass(frozen=True)
class PostScore:
    post_id: int
    engagement_score: float
    engagement_rate: float | None
    metrics_complete: bool


@dataclass
class ScoreRunResult:
    run_id: int
    posts_scored: int
    with_rate: int
    incomplete_metrics: int


def load_weights(app_config: AppConfig | None = None) -> dict[str, float]:
    app_config = app_config or get_app_config()
    configured = (app_config.engagement or {}).get("weights", {})
    return {key: float(configured.get(key, default)) for key, default in _DEFAULT_WEIGHTS.items()}


def score_post(
    *,
    reactions: int | None,
    comments: int | None,
    reposts: int | None,
    weights: dict[str, float],
) -> tuple[float, bool]:
    """Return ``(engagement_score, metrics_complete)``. Missing metrics are treated as 0."""
    metrics_complete = None not in (reactions, comments, reposts)
    score = (
        weights["reactions"] * (reactions or 0)
        + weights["comments"] * (comments or 0)
        + weights["reposts"] * (reposts or 0)
    )
    return float(score), metrics_complete


def engagement_rate(score: float, followers: int | None) -> float | None:
    """Follower-normalised rate as a percentage, or ``None`` when followers are unknown."""
    if not followers or followers <= 0:
        return None
    return score / followers * 100.0


def score_run(
    session: Session,
    *,
    run_id: int,
    app_config: AppConfig | None = None,
    set_stage: bool = True,
) -> ScoreRunResult:
    """Compute and persist engagement score + rate for every classified post in the run."""
    app_config = app_config or get_app_config()
    weights = load_weights(app_config)
    repo = AnalysisRepo(session)

    if set_stage:
        RunRepo(session).set_stage(run_id, "score")

    scores: dict[int, PostScore] = {}
    for row in repo.metrics_for_run(run_id):
        score, complete = score_post(
            reactions=row.reactions,
            comments=row.comments,
            reposts=row.reposts,
            weights=weights,
        )
        rate = engagement_rate(score, row.followers)
        scores[row.post_id] = PostScore(row.post_id, score, rate, complete)

    repo.set_post_scores(scores)
    session.flush()

    result = ScoreRunResult(
        run_id=run_id,
        posts_scored=len(scores),
        with_rate=sum(1 for s in scores.values() if s.engagement_rate is not None),
        incomplete_metrics=sum(1 for s in scores.values() if not s.metrics_complete),
    )
    log.info(
        "engagement_scored",
        run_id=run_id,
        posts=result.posts_scored,
        with_rate=result.with_rate,
        incomplete=result.incomplete_metrics,
    )
    return result
