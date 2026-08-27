"""Cross-competitor intelligence (brief step 9, EPIC-05).

Pure computation over the run's scored posts — no LLM. Produces:

* **common_themes** — topics several competitors all cover.
* **saturated_topics** — common *and* above-median in post share.
* **white_spaces** — taxonomy topics almost nobody covers, plus topics that punch above
  the median on engagement while sitting below it on frequency.
* **opportunity_topics** — the quantified version of the latter: engagement above the
  median topic, coverage below it.
* **format_opportunities** — formats whose average engagement is a configurable multiple
  of the overall average while still a minority of posts (e.g. "video = 8% of posts,
  2.4x engagement").
* **keyword_matrix** — every keyword placed in a frequency-vs-performance quadrant, so
  "what they talk about most" and "what actually lands" can diverge on the dashboard.

All thresholds (median splits, minimum sample sizes, multipliers) come from
``config/app.yaml: cross``.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from statistics import median

from sqlalchemy.orm import Session

from app.config.settings import AppConfig, get_app_config, get_taxonomies
from app.core.logging import get_logger
from app.db.repos import AnalysisRepo, RunRepo
from app.schemas.strategy_map import (
    CrossCompetitorInsights,
    FormatOpportunity,
    KeywordPerf,
    OpportunityTopic,
    ThemeStat,
    WhiteSpace,
)

log = get_logger(__name__)


def _mean(values: list[float]) -> float:
    return sum(values) / len(values) if values else 0.0


@dataclass(frozen=True)
class _Row:
    competitor_id: int
    topic: str | None
    format: str | None
    score: float
    terms: list[str]


def _load_rows(session: Session, run_id: int) -> list[_Row]:
    rows: list[_Row] = []
    for r in AnalysisRepo(session).scored_rows_for_run(run_id):
        terms = sorted(
            {k.get("term", "").strip().lower() for k in (r.keywords or []) if k.get("term")}
        )
        rows.append(
            _Row(
                competitor_id=r.competitor_id,
                topic=r.topic,
                format=r.format,
                score=r.engagement_score or 0.0,
                terms=[t for t in terms if t],
            )
        )
    return rows


@dataclass
class _TopicAgg:
    posts: int
    competitors: set
    scores: list[float]

    @property
    def avg(self) -> float:
        return _mean(self.scores)


def _topic_aggs(rows: list[_Row]) -> dict[str, _TopicAgg]:
    aggs: dict[str, _TopicAgg] = {}
    for row in rows:
        if row.topic is None:
            continue
        agg = aggs.setdefault(row.topic, _TopicAgg(0, set(), []))
        agg.posts += 1
        agg.competitors.add(row.competitor_id)
        agg.scores.append(row.score)
    return aggs


def compute_cross_insights(
    rows: list[_Row], *, cfg: dict, taxonomy_topics: list[str]
) -> CrossCompetitorInsights:
    total = len(rows)
    if total == 0:
        return CrossCompetitorInsights()

    overall_avg = _mean([r.score for r in rows])
    aggs = _topic_aggs(rows)
    shares = {t: a.posts / total for t, a in aggs.items()}
    median_share = median(shares.values()) if shares else 0.0
    median_engagement = median([a.avg for a in aggs.values()]) if aggs else 0.0

    common_min = int(cfg.get("common_min_competitors", 2))
    sat_min = int(cfg.get("saturation_min_competitors", 3))
    ws_max = int(cfg.get("whitespace_max_competitors", 1))
    fmt_mult = float(cfg.get("format_opportunity_multiplier", 2.0))
    fmt_max_share = float(cfg.get("format_opportunity_max_share", 0.25))
    kw_min_freq = int(cfg.get("keyword_min_frequency", 2))

    def theme_stat(topic: str) -> ThemeStat:
        agg = aggs[topic]
        return ThemeStat(
            topic=topic,
            competitors_covering=len(agg.competitors),
            post_share=round(shares[topic], 4),
            avg_engagement=round(agg.avg, 2),
        )

    common_themes = sorted(
        (theme_stat(t) for t, a in aggs.items() if len(a.competitors) >= common_min),
        key=lambda s: (-s.competitors_covering, -s.post_share, s.topic),
    )
    saturated_topics = sorted(
        (
            theme_stat(t)
            for t, a in aggs.items()
            if len(a.competitors) >= sat_min and shares[t] >= median_share
        ),
        key=lambda s: (-s.post_share, s.topic),
    )

    # white spaces: taxonomy topics nobody (or almost nobody) covers ...
    white_spaces: list[WhiteSpace] = []
    seen_ws: set[str] = set()
    for topic in taxonomy_topics:
        if topic == "other":
            continue
        agg = aggs.get(topic)
        covering = len(agg.competitors) if agg else 0
        if covering <= ws_max:
            white_spaces.append(
                WhiteSpace(
                    topic=topic,
                    reason="low_coverage",
                    competitors_covering=covering,
                    post_share=round(shares.get(topic, 0.0), 4),
                    avg_engagement=round(agg.avg if agg else 0.0, 2),
                )
            )
            seen_ws.add(topic)
    # ... plus covered topics that over-perform on engagement but under-index on frequency
    for topic, agg in aggs.items():
        if topic in seen_ws or topic == "other":
            continue
        if agg.avg > median_engagement and shares[topic] < median_share:
            white_spaces.append(
                WhiteSpace(
                    topic=topic,
                    reason="high_engagement_low_frequency",
                    competitors_covering=len(agg.competitors),
                    post_share=round(shares[topic], 4),
                    avg_engagement=round(agg.avg, 2),
                )
            )
    white_spaces.sort(key=lambda w: (-w.avg_engagement, w.topic))

    opportunity_topics = sorted(
        (
            OpportunityTopic(
                topic=topic,
                avg_engagement=round(agg.avg, 2),
                post_share=round(shares[topic], 4),
                engagement_vs_median=round(agg.avg - median_engagement, 2),
                coverage_vs_median=round(shares[topic] - median_share, 4),
            )
            for topic, agg in aggs.items()
            if topic != "other" and agg.avg > median_engagement and shares[topic] < median_share
        ),
        key=lambda o: (-o.engagement_vs_median, o.topic),
    )

    # format opportunities
    fmt_scores: dict[str, list[float]] = defaultdict(list)
    for row in rows:
        if row.format is not None:
            fmt_scores[row.format].append(row.score)
    format_opportunities: list[FormatOpportunity] = []
    for fmt, scores in fmt_scores.items():
        avg = _mean(scores)
        multiplier = avg / overall_avg if overall_avg else 0.0
        share = len(scores) / total
        if multiplier >= fmt_mult and share <= fmt_max_share:
            format_opportunities.append(
                FormatOpportunity(
                    format=fmt,
                    post_share=round(share, 4),
                    avg_engagement=round(avg, 2),
                    overall_avg_engagement=round(overall_avg, 2),
                    engagement_multiplier=round(multiplier, 2),
                )
            )
    format_opportunities.sort(key=lambda f: (-f.engagement_multiplier, f.format))

    keyword_matrix = _keyword_matrix(rows, min_freq=kw_min_freq)

    return CrossCompetitorInsights(
        common_themes=common_themes,
        saturated_topics=saturated_topics,
        white_spaces=white_spaces,
        opportunity_topics=opportunity_topics,
        format_opportunities=format_opportunities,
        keyword_matrix=keyword_matrix,
    )


def _keyword_matrix(rows: list[_Row], *, min_freq: int) -> list[KeywordPerf]:
    freq: dict[str, int] = defaultdict(int)
    scores: dict[str, list[float]] = defaultdict(list)
    for row in rows:
        for term in set(row.terms):
            freq[term] += 1
            scores[term].append(row.score)
    terms = [t for t, f in freq.items() if f >= min_freq]
    if not terms:
        return []
    avg_perf = {t: _mean(scores[t]) for t in terms}
    median_freq = median([freq[t] for t in terms])
    median_perf = median(avg_perf.values())
    out: list[KeywordPerf] = []
    for term in terms:
        hi_freq = freq[term] >= median_freq
        hi_perf = avg_perf[term] >= median_perf
        quadrant = f"{'high' if hi_freq else 'low'}_freq_{'high' if hi_perf else 'low'}_perf"
        out.append(
            KeywordPerf(
                term=term,
                frequency=freq[term],
                avg_engagement=round(avg_perf[term], 2),
                quadrant=quadrant,  # type: ignore[arg-type]
            )
        )
    out.sort(key=lambda k: (-k.frequency, k.term))
    return out


@dataclass
class CrossRunResult:
    run_id: int
    insights: CrossCompetitorInsights


def build_cross_insights(
    session: Session,
    *,
    run_id: int,
    app_config: AppConfig | None = None,
    set_stage: bool = True,
) -> CrossRunResult:
    app_config = app_config or get_app_config()
    if set_stage:
        RunRepo(session).set_stage(run_id, "cross")
    rows = _load_rows(session, run_id)
    insights = compute_cross_insights(
        rows,
        cfg=app_config.cross or {},
        taxonomy_topics=get_taxonomies().topics,
    )
    log.info(
        "cross_insights_built",
        run_id=run_id,
        common=len(insights.common_themes),
        white_spaces=len(insights.white_spaces),
        format_opportunities=len(insights.format_opportunities),
        keywords=len(insights.keyword_matrix),
    )
    return CrossRunResult(run_id=run_id, insights=insights)
