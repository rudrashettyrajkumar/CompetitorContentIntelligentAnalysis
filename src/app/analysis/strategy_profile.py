"""Per-competitor strategy profiles (brief step 8, EPIC-05).

Everything here is deterministic computation over the run's scored posts — themes by
post share, a format-group content mix, best format/topic by average engagement (with a
sample-size floor), posting cadence, and the day-of-week engagement windows. The only
LLM touch is a 2-3 sentence ``positioning_summary`` per competitor
(``prompts/analysis/positioning_summary``); under FakeLLM it is produced offline.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.config.settings import AppConfig, get_app_config
from app.core.logging import get_logger
from app.core.model_router import LLMError, ModelRouter
from app.core.prompt_registry import PromptRegistry
from app.db.repos import AnalysisRepo, RunRepo
from app.schemas.strategy_map import PositioningSummary, StrategyProfile

log = get_logger(__name__)

POSITIONING_PROMPT = "positioning_summary"
_WEEKDAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]


@dataclass(frozen=True)
class _Row:
    competitor_id: int
    competitor_name: str
    posted_at: object
    format: str | None
    topic: str | None
    score: float


def _mean(values: list[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def format_group_map(app_config: AppConfig) -> dict[str, str]:
    """Invert ``config: format_groups`` into ``{format: group}``; unmapped -> ``other``."""
    out: dict[str, str] = {}
    for group, formats in (app_config.format_groups or {}).items():
        for fmt in formats:
            out[fmt] = group
    return out


def content_mix(rows: list[_Row], group_map: dict[str, str]) -> dict[str, float]:
    """Percent of posts per format group. Percentages sum to 100 (±rounding)."""
    groups = sorted({*group_map.values(), "other"})
    counts = {g: 0 for g in groups}
    total = 0
    for row in rows:
        if row.format is None:
            continue
        counts[group_map.get(row.format, "other")] += 1
        total += 1
    if total == 0:
        return {g: 0.0 for g in groups}
    return {g: round(counts[g] / total * 100, 2) for g in groups}


def _best_by_avg(rows: list[_Row], attr: str, min_posts: int) -> str | None:
    buckets: dict[str, list[float]] = defaultdict(list)
    for row in rows:
        key = getattr(row, attr)
        if key is not None:
            buckets[key].append(row.score)
    eligible = {k: _mean(v) for k, v in buckets.items() if len(v) >= min_posts}
    if not eligible:
        return None
    return max(sorted(eligible), key=lambda k: eligible[k])


def primary_themes(rows: list[_Row], limit: int = 3) -> list[str]:
    counts: dict[str, int] = defaultdict(int)
    for row in rows:
        if row.topic is not None:
            counts[row.topic] += 1
    ordered = sorted(counts, key=lambda k: (-counts[k], k))
    return ordered[:limit]


def engagement_windows(rows: list[_Row], limit: int = 3) -> list[str]:
    """Top weekdays by average engagement score, most-engaging first."""
    by_day: dict[int, list[float]] = defaultdict(list)
    for row in rows:
        by_day[row.posted_at.weekday()].append(row.score)
    ranked = sorted(by_day, key=lambda d: (-_mean(by_day[d]), d))
    return [_WEEKDAYS[d] for d in ranked[:limit]]


def posting_frequency_per_week(post_count: int, period_days: int) -> float:
    weeks = max(period_days, 1) / 7.0
    return round(post_count / weeks, 2)


def _positioning_summary(
    profile: StrategyProfile,
    *,
    router: ModelRouter,
    registry: PromptRegistry,
) -> str:
    rendered = registry.render(
        POSITIONING_PROMPT,
        competitor=profile.competitor,
        primary_themes=profile.primary_themes,
        content_mix=profile.content_mix,
        best_format=profile.best_format or "n/a",
        best_topic=profile.best_topic or "n/a",
        posting_frequency_per_week=profile.posting_frequency_per_week,
        engagement_windows=profile.engagement_windows,
    )
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
        return result.summary.strip() if isinstance(result, PositioningSummary) else ""
    except LLMError as exc:
        log.warning("positioning_summary_failed", competitor=profile.competitor, error=str(exc))
        return ""


@dataclass
class ProfileRunResult:
    run_id: int
    profiles: list[StrategyProfile]


def build_strategy_profiles(
    session: Session,
    *,
    run_id: int,
    router: ModelRouter,
    registry: PromptRegistry,
    app_config: AppConfig | None = None,
    set_stage: bool = True,
) -> ProfileRunResult:
    app_config = app_config or get_app_config()
    cfg = app_config.cross or {}
    min_posts_for_best = int(cfg.get("min_posts_for_best", 3))
    group_map = format_group_map(app_config)

    if set_stage:
        RunRepo(session).set_stage(run_id, "profiles")

    run = RunRepo(session).get(run_id)
    period_days = run.period_days if run else 30

    grouped: dict[int, list[_Row]] = defaultdict(list)
    names: dict[int, str] = {}
    for r in AnalysisRepo(session).scored_rows_for_run(run_id):
        grouped[r.competitor_id].append(
            _Row(
                competitor_id=r.competitor_id,
                competitor_name=r.competitor_name,
                posted_at=r.posted_at,
                format=r.format,
                topic=r.topic,
                score=r.engagement_score or 0.0,
            )
        )
        names[r.competitor_id] = r.competitor_name

    profiles: list[StrategyProfile] = []
    for competitor_id in sorted(grouped):
        rows = grouped[competitor_id]
        profile = StrategyProfile(
            competitor=names[competitor_id],
            competitor_id=competitor_id,
            primary_themes=primary_themes(rows),
            content_mix=content_mix(rows, group_map),
            best_format=_best_by_avg(rows, "format", min_posts_for_best),
            best_topic=_best_by_avg(rows, "topic", min_posts_for_best),
            posting_frequency_per_week=posting_frequency_per_week(len(rows), period_days),
            engagement_windows=engagement_windows(rows),
        )
        profile.positioning_summary = _positioning_summary(
            profile, router=router, registry=registry
        )
        profiles.append(profile)

    log.info("strategy_profiles_built", run_id=run_id, competitors=len(profiles))
    return ProfileRunResult(run_id=run_id, profiles=profiles)
