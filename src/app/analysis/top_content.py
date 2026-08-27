"""Top content report (brief step 10, EPIC-05).

Rank the run's posts across all competitors and take the top N (``config: cross
.top_content_size``). Ranking strategy — documented here because free-tier follower
data is patchy:

* If **every** scored post in the run carries an ``engagement_rate`` (follower count was
  known for all competitors), rank by ``engagement_rate`` — the fair, size-normalised
  measure.
* Otherwise rank by raw ``engagement_score``. Mixing the two would let a large-follower
  competitor's absolute numbers crowd out everyone else, or vice-versa, so we pick one
  consistent key for the whole report and record which in ``ranked_by``.

Each selected post gets an LLM ``WhyItWorked`` breakdown via
``prompts/analysis/why_it_worked`` in batches of ``config: cross.why_it_worked_batch``.
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.config.settings import AppConfig, get_app_config
from app.core.logging import get_logger
from app.core.model_router import LLMError, ModelRouter
from app.core.prompt_registry import PromptRegistry
from app.db.repos import AnalysisRepo, RunRepo
from app.schemas.strategy_map import (
    TopContentItem,
    TopContentReport,
    WhyItWorked,
    WhyItWorkedBatch,
)

log = get_logger(__name__)

WHY_PROMPT = "why_it_worked"

_FALLBACK_WHY = WhyItWorked(
    hook="not analysed",
    structure="not analysed",
    visual_format="not analysed",
    cta_assessment="not analysed",
    audience_relevance="not analysed",
    length_note="not analysed",
    summary="analysis unavailable",
)


@dataclass(frozen=True)
class _Candidate:
    post_id: int
    competitor: str
    url: str
    posted_at: object
    format: str | None
    topic: str | None
    score: float
    rate: float | None


def _load_candidates(session: Session, run_id: int) -> list[_Candidate]:
    return [
        _Candidate(
            post_id=r.post_id,
            competitor=r.competitor_name,
            url=r.url,
            posted_at=r.posted_at,
            format=r.format,
            topic=r.topic,
            score=r.engagement_score or 0.0,
            rate=r.engagement_rate,
        )
        for r in AnalysisRepo(session).scored_rows_for_run(run_id)
    ]


def rank_candidates(candidates: list[_Candidate], size: int) -> tuple[list[_Candidate], str]:
    """Return ``(top_n, ranked_by)``. See module docstring for the strategy."""
    ranked_by = (
        "engagement_rate"
        if candidates and all(c.rate is not None for c in candidates)
        else "engagement_score"
    )
    key = (
        (lambda c: (-(c.rate or 0.0), c.post_id))
        if ranked_by == "engagement_rate"
        else (lambda c: (-c.score, c.post_id))
    )
    return sorted(candidates, key=key)[: max(0, size)], ranked_by


def _analyse_batch(
    batch: list[_Candidate],
    contents: dict[int, str],
    *,
    router: ModelRouter,
    registry: PromptRegistry,
) -> dict[int, WhyItWorked]:
    posts = [
        {
            "index": i,
            "competitor": c.competitor,
            "format": c.format or "unknown",
            "topic": c.topic or "other",
            "date": c.posted_at.date().isoformat(),
            "engagement_score": round(c.score, 1),
            "content": contents.get(c.post_id, ""),
        }
        for i, c in enumerate(batch)
    ]
    rendered = registry.render(WHY_PROMPT, posts=posts)
    try:
        result = router.invoke(
            tier=rendered.meta.model_tier,
            system=rendered.system,
            user=rendered.user,
            schema=rendered.schema,
            temperature=rendered.meta.temperature,
            prompt_name=rendered.meta.name,
            prompt_version=rendered.meta.version,
        )
    except LLMError as exc:
        log.warning("why_it_worked_batch_failed", size=len(batch), error=str(exc))
        return {}
    if not isinstance(result, WhyItWorkedBatch):
        return {}
    out: dict[int, WhyItWorked] = {}
    for row in result.results:
        if 0 <= row.index < len(batch):
            out[batch[row.index].post_id] = WhyItWorked(**row.model_dump(exclude={"index"}))
    return out


@dataclass
class TopContentRunResult:
    run_id: int
    report: TopContentReport


def build_top_content(
    session: Session,
    *,
    run_id: int,
    router: ModelRouter,
    registry: PromptRegistry,
    app_config: AppConfig | None = None,
    set_stage: bool = True,
) -> TopContentRunResult:
    app_config = app_config or get_app_config()
    cfg = app_config.cross or {}
    size = int(cfg.get("top_content_size", 20))
    batch_size = max(1, int(cfg.get("why_it_worked_batch", 5)))

    if set_stage:
        RunRepo(session).set_stage(run_id, "top_content")

    top, ranked_by = rank_candidates(_load_candidates(session, run_id), size)

    from app.db.models import Post

    contents = {
        pid: (post.content or "")
        for pid in (c.post_id for c in top)
        if (post := session.get(Post, pid)) is not None
    }

    why_by_post: dict[int, WhyItWorked] = {}
    for start in range(0, len(top), batch_size):
        batch = top[start : start + batch_size]
        why_by_post.update(_analyse_batch(batch, contents, router=router, registry=registry))

    items = [
        TopContentItem(
            rank=i + 1,
            post_id=c.post_id,
            competitor=c.competitor,
            url=c.url,
            posted_at=c.posted_at,
            format=c.format,
            topic=c.topic,
            engagement_score=round(c.score, 2),
            engagement_rate=c.rate,
            ranked_by=ranked_by,  # type: ignore[arg-type]
            why=why_by_post.get(c.post_id, _FALLBACK_WHY),
        )
        for i, c in enumerate(top)
    ]
    report = TopContentReport(ranked_by=ranked_by, items=items)  # type: ignore[arg-type]
    log.info(
        "top_content_built",
        run_id=run_id,
        items=len(items),
        ranked_by=ranked_by,
        analysed=sum(1 for it in items if it.why is not _FALLBACK_WHY),
    )
    return TopContentRunResult(run_id=run_id, report=report)
