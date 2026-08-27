"""Assemble the structured intelligence the strategy layer reasons over (EPIC-06).

One fetch per run, turned into:

* ``company`` — our profile (``config/company.yaml``).
* ``profiles`` / ``cross`` / ``top_content`` — the EPIC-05 outputs (profiles from
  ``strategy_profiles``; cross + top-content re-hydrated from ``insights``).
* ``campaigns`` — competitor campaign records for the run.
* ``competitor_texts`` — every raw post body in the run, used by the originality guard.
* ``topic_stats`` — per-topic volume / coverage / engagement, plus the cross-insight
  quadrant flags. The signal-derivation rules stamp opportunity fields from *this*, so
  they stay reproducible from the same data the agent saw.
"""

from __future__ import annotations

from dataclasses import dataclass
from statistics import median

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.analysis.cross import _load_rows, _topic_aggs
from app.config.settings import CompanyContext, get_company_context
from app.db.models import Post
from app.db.repos import CampaignRepo, InsightRepo, StrategyProfileRepo
from app.schemas.strategy_map import (
    CrossCompetitorInsights,
    StrategyProfile,
    TopContentReport,
)


@dataclass(frozen=True)
class TopicStat:
    topic: str
    post_count: int
    post_share: float
    competitors_covering: int
    avg_engagement: float
    above_median_engagement: bool
    is_opportunity: bool
    is_white_space: bool


@dataclass
class StrategyInputs:
    run_id: int
    company: CompanyContext
    profiles: list[StrategyProfile]
    cross: CrossCompetitorInsights
    top_content: TopContentReport
    campaigns: list[dict]
    competitor_texts: list[str]
    topic_stats: dict[str, TopicStat]
    n_competitors: int = 0

    def keyword_terms(self) -> list[str]:
        return [k.term for k in self.cross.keyword_matrix]

    def as_agent_files(self) -> dict[str, str]:
        """Virtual-FS payload for the deep agent: one JSON blob per input section."""
        import json

        return {
            "company_context.json": self.company.model_dump_json(indent=2),
            "strategy_profiles.json": json.dumps(
                [p.model_dump(mode="json") for p in self.profiles], indent=2
            ),
            "cross_insights.json": self.cross.model_dump_json(indent=2),
            "top_content.json": self.top_content.model_dump_json(indent=2),
            "campaigns.json": json.dumps(self.campaigns, indent=2, default=str),
            "topic_stats.json": json.dumps(
                {t: vars(s) for t, s in self.topic_stats.items()}, indent=2
            ),
        }


def _topic_stats(
    session: Session, run_id: int, cross: CrossCompetitorInsights
) -> dict[str, TopicStat]:
    rows = _load_rows(session, run_id)
    total = len(rows) or 1
    aggs = _topic_aggs(rows)
    if aggs:
        med = median([a.avg for a in aggs.values()])
    else:
        med = 0.0
    opp_topics = {o.topic for o in cross.opportunity_topics}
    ws_topics = {w.topic for w in cross.white_spaces}
    out: dict[str, TopicStat] = {}
    for topic, agg in aggs.items():
        out[topic] = TopicStat(
            topic=topic,
            post_count=agg.posts,
            post_share=round(agg.posts / total, 4),
            competitors_covering=len(agg.competitors),
            avg_engagement=round(agg.avg, 2),
            above_median_engagement=agg.avg >= med,
            is_opportunity=topic in opp_topics,
            is_white_space=topic in ws_topics,
        )
    return out


def assemble_strategy_inputs(session: Session, *, run_id: int) -> StrategyInputs:
    cross_payload = InsightRepo(session).get_payload(run_id, "cross_competitor") or {}
    top_payload = InsightRepo(session).get_payload(run_id, "top_content") or {
        "ranked_by": "engagement_score",
        "items": [],
    }
    cross = CrossCompetitorInsights.model_validate(cross_payload)
    top_content = TopContentReport.model_validate(top_payload)

    profile_rows = StrategyProfileRepo(session).list_for_run(run_id)
    profiles = [
        StrategyProfile(
            competitor=_competitor_name(session, r.competitor_id),
            competitor_id=r.competitor_id,
            primary_themes=list(r.primary_themes or []),
            content_mix=dict(r.content_mix or {}),
            best_format=r.best_format,
            best_topic=r.best_topic,
            posting_frequency_per_week=r.posting_frequency_per_week or 0.0,
            engagement_windows=list(r.engagement_windows or []),
            positioning_summary=r.positioning_summary or "",
        )
        for r in profile_rows
    ]

    campaigns = [
        {
            "name": c.name,
            "theme": c.theme,
            "objective": c.objective,
            "formats": c.formats,
            "keywords": c.keywords,
            "hashtags": c.hashtags,
            "cta": c.cta,
            "target_audience": c.target_audience,
            "total_engagement": c.total_engagement,
            "post_count": len(c.post_ids or []),
        }
        for c in CampaignRepo(session).list_for_run(run_id)
    ]

    texts = list(session.scalars(select(Post.content).where(Post.run_id == run_id)).all())

    return StrategyInputs(
        run_id=run_id,
        company=get_company_context(),
        profiles=profiles,
        cross=cross,
        top_content=top_content,
        campaigns=campaigns,
        competitor_texts=[t for t in texts if t],
        topic_stats=_topic_stats(session, run_id, cross),
        n_competitors=len(profile_rows),
    )


def _competitor_name(session: Session, competitor_id: int) -> str:
    from app.db.models import Competitor

    comp = session.get(Competitor, competitor_id)
    return comp.name if comp else f"competitor {competitor_id}"
