"""Read-side service for the ``/api/results`` and ``/api/exports`` routes (EPIC-07).

Turns the run's persisted rows (posts + intelligence, campaigns, strategy profiles,
insight bundles) into JSON-ready dicts. No writes, no LLM.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.db.repos import (
    AnalysisRepo,
    CampaignRepo,
    CompetitorRepo,
    InsightRepo,
    PostRepo,
    RunRepo,
    StrategyProfileRepo,
)

_SECTIONS = (
    "posts",
    "formats",
    "topics",
    "keywords",
    "campaigns",
    "profiles",
    "cross",
    "top-content",
    "strategy",
    "opportunities",
    "calendar",
)

_POST_SORT_FIELDS = {
    "engagement_score",
    "engagement_rate",
    "posted_at",
    "competitor_name",
    "format",
    "topic",
}


class RunNotFound(Exception):
    pass


class RunNotReady(Exception):
    def __init__(self, status: str) -> None:
        self.status = status
        super().__init__(f"run is {status}, results not available yet")


@dataclass
class PostQuery:
    limit: int = 50
    offset: int = 0
    competitor_id: int | None = None
    format: str | None = None
    topic: str | None = None
    sort: str = "engagement_score"
    order: str = "desc"


class ResultsService:
    def __init__(self, session: Session) -> None:
        self.session = session

    # -- guards --------------------------------------------------------- #
    def require_completed_run(self, run_id: int):
        run = RunRepo(self.session).get(run_id)
        if run is None:
            raise RunNotFound(str(run_id))
        if run.status != "completed":
            raise RunNotReady(run.status)
        return run

    # -- posts --------------------------------------------------------- #
    def posts(self, run_id: int, q: PostQuery) -> dict:
        rows = AnalysisRepo(self.session).scored_rows_for_run(run_id)
        items = [
            {
                "post_id": r.post_id,
                "competitor_id": r.competitor_id,
                "competitor_name": r.competitor_name,
                "url": r.url,
                "posted_at": r.posted_at.isoformat(),
                "format": r.format,
                "topic": r.topic,
                "sub_topic": r.sub_topic,
                "cta": r.cta,
                "keywords": [k.get("term") for k in (r.keywords or []) if k.get("term")],
                "engagement_score": r.engagement_score or 0.0,
                "engagement_rate": r.engagement_rate,
                "metrics_complete": bool(r.metrics_complete),
            }
            for r in rows
        ]
        if q.competitor_id is not None:
            items = [it for it in items if it["competitor_id"] == q.competitor_id]
        if q.format:
            items = [it for it in items if it["format"] == q.format]
        if q.topic:
            items = [it for it in items if it["topic"] == q.topic]

        sort_key = q.sort if q.sort in _POST_SORT_FIELDS else "engagement_score"
        reverse = q.order != "asc"
        items.sort(key=lambda it: (it.get(sort_key) is None, it.get(sort_key)), reverse=reverse)

        total = len(items)
        window = items[q.offset : q.offset + q.limit]
        return {
            "total": total,
            "limit": q.limit,
            "offset": q.offset,
            "items": window,
        }

    # -- ranking sections ------------------------------------------------ #
    def formats(self, run_id: int) -> list[dict]:
        return [r.model_dump() for r in AnalysisRepo(self.session).top_formats(run_id)]

    def topics(self, run_id: int) -> list[dict]:
        return [r.model_dump() for r in AnalysisRepo(self.session).top_topics(run_id)]

    def ctas(self, run_id: int) -> list[dict]:
        return [r.model_dump() for r in AnalysisRepo(self.session).top_ctas(run_id)]

    def keywords(self, run_id: int) -> list[dict]:
        cross = InsightRepo(self.session).get_payload(run_id, "cross_competitor") or {}
        return cross.get("keyword_matrix", [])

    def campaigns(self, run_id: int) -> list[dict]:
        return [
            {
                "id": c.id,
                "competitor_id": c.competitor_id,
                "name": c.name,
                "theme": c.theme,
                "objective": c.objective,
                "post_ids": c.post_ids or [],
                "start_date": c.start_date.isoformat() if c.start_date else None,
                "end_date": c.end_date.isoformat() if c.end_date else None,
                "formats": c.formats or [],
                "keywords": c.keywords or [],
                "hashtags": c.hashtags or [],
                "cta": c.cta,
                "target_audience": c.target_audience,
                "total_engagement": c.total_engagement,
                "top_post_id": c.top_post_id,
                "performance_summary": c.performance_summary,
            }
            for c in CampaignRepo(self.session).list_for_run(run_id)
        ]

    def profiles(self, run_id: int) -> list[dict]:
        names = {c.id: c.name for c in CompetitorRepo(self.session).list_all(status=None)}
        return [
            {
                "competitor_id": p.competitor_id,
                "competitor": names.get(p.competitor_id, f"competitor {p.competitor_id}"),
                "primary_themes": p.primary_themes or [],
                "content_mix": p.content_mix or {},
                "best_format": p.best_format,
                "best_topic": p.best_topic,
                "posting_frequency_per_week": p.posting_frequency_per_week,
                "engagement_windows": p.engagement_windows or [],
                "positioning_summary": p.positioning_summary,
            }
            for p in StrategyProfileRepo(self.session).list_for_run(run_id)
        ]

    def _insight(self, run_id: int, kind: str):
        return InsightRepo(self.session).get_payload(run_id, kind)

    def cross(self, run_id: int):
        return self._insight(run_id, "cross_competitor") or {}

    def top_content(self, run_id: int):
        return self._insight(run_id, "top_content") or {}

    def strategy(self, run_id: int):
        return self._insight(run_id, "strategy") or {}

    def opportunities(self, run_id: int):
        return self._insight(run_id, "opportunities") or {}

    def calendar(self, run_id: int):
        return self._insight(run_id, "calendar") or {}

    def diff(self, run_id: int):
        return self._insight(run_id, "period_diff")

    def change_report(self, run_id: int):
        return self._insight(run_id, "change_report")

    # -- summary KPI block -------------------------------------------- #
    def summary(self, run_id: int) -> dict:
        rows = AnalysisRepo(self.session).scored_rows_for_run(run_id)
        run = RunRepo(self.session).get(run_id)
        total_posts = PostRepo(self.session).count_for_run(run_id)
        period_days = run.period_days if run else 30

        scores = [r.engagement_score or 0.0 for r in rows]
        rates = [r.engagement_rate for r in rows if r.engagement_rate is not None]
        by_competitor: dict[str, float] = defaultdict(float)
        for r in rows:
            by_competitor[r.competitor_name] += r.engagement_score or 0.0

        formats = AnalysisRepo(self.session).top_formats(run_id)
        topics = AnalysisRepo(self.session).top_topics(run_id)
        kw_counter: Counter = Counter()
        for r in rows:
            for k in r.keywords or []:
                if k.get("term"):
                    kw_counter[k["term"]] += 1

        return {
            "run_id": run_id,
            "period_days": period_days,
            "competitors_analyzed": len({r.competitor_id for r in rows}),
            "total_posts": total_posts,
            "posts_per_week": round(total_posts / (max(period_days, 1) / 7), 2),
            "avg_engagement_score": round(sum(scores) / len(scores), 2) if scores else 0.0,
            "avg_engagement_rate": round(sum(rates) / len(rates), 4) if rates else None,
            "top_competitor": max(by_competitor, key=by_competitor.get) if by_competitor else None,
            "top_topic": topics[0].topic if topics else None,
            "top_format": formats[0].format if formats else None,
            "top_keywords": [t for t, _ in kw_counter.most_common(10)],
            "campaign_count": CampaignRepo(self.session).count_for_run(run_id),
        }

    # -- full bundle (exports) -------------------------------------- #
    def bundle(self, run_id: int) -> dict:
        return {
            "summary": self.summary(run_id),
            "posts": self.posts(run_id, PostQuery(limit=100_000)),
            "formats": self.formats(run_id),
            "topics": self.topics(run_id),
            "ctas": self.ctas(run_id),
            "keywords": self.keywords(run_id),
            "campaigns": self.campaigns(run_id),
            "profiles": self.profiles(run_id),
            "cross": self.cross(run_id),
            "top_content": self.top_content(run_id),
            "strategy": self.strategy(run_id),
            "opportunities": self.opportunities(run_id),
            "calendar": self.calendar(run_id),
        }


SECTIONS = _SECTIONS
