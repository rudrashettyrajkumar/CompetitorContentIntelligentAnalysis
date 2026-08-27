"""Repositories own every query. Feature code never touches SQLAlchemy directly.

EPIC-01 ships CompetitorRepo and RunRepo; EPIC-02 adds ProfileRepo and PostRepo;
EPIC-03 adds PostIntelligenceRepo; EPIC-04 adds AnalysisRepo and CampaignRepo.
"""

from collections import defaultdict
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.models import (
    Campaign,
    CompanyProfile,
    Competitor,
    Insight,
    Post,
    PostIntelligence,
    Run,
)
from app.db.models import StrategyProfile as StrategyProfileRow
from app.schemas.analysis import (
    CompetitorTopPosts,
    CtaPerformance,
    FormatPerformance,
    TopicPerformance,
    TopPost,
    ValidatedCampaign,
)
from app.schemas.collection import CompanyProfile as CompanyProfileIn
from app.schemas.collection import RawPost
from app.schemas.intelligence import PostClassification


class CompetitorRepo:
    def __init__(self, session: Session) -> None:
        self.session = session

    def upsert(self, **fields) -> Competitor:
        """Insert or update by canonical linkedin_url."""
        url = fields["linkedin_url"]
        existing = self.session.scalar(select(Competitor).where(Competitor.linkedin_url == url))
        if existing:
            for key, value in fields.items():
                setattr(existing, key, value)
            self.session.flush()
            return existing
        competitor = Competitor(**fields)
        self.session.add(competitor)
        self.session.flush()
        return competitor

    def get(self, competitor_id: int) -> Competitor | None:
        return self.session.get(Competitor, competitor_id)

    def list_all(self, status: str | None = "active") -> list[Competitor]:
        stmt = select(Competitor).order_by(Competitor.name)
        if status:
            stmt = stmt.where(Competitor.status == status)
        return list(self.session.scalars(stmt))

    def delete(self, competitor_id: int) -> bool:
        competitor = self.get(competitor_id)
        if competitor is None:
            return False
        self.session.delete(competitor)
        self.session.flush()
        return True


class RunRepo:
    def __init__(self, session: Session) -> None:
        self.session = session

    def create(
        self,
        *,
        period_days: int,
        adapter: str,
        trigger: str = "manual",
        competitor_ids: list[int] | None = None,
    ) -> Run:
        run = Run(
            period_days=period_days,
            adapter=adapter,
            status="pending",
            trigger=trigger,
            competitor_ids=list(competitor_ids) if competitor_ids else None,
        )
        self.session.add(run)
        self.session.flush()
        return run

    def get(self, run_id: int) -> Run | None:
        return self.session.get(Run, run_id)

    def list_all(self) -> list[Run]:
        return list(self.session.scalars(select(Run).order_by(Run.started_at.desc())))

    def latest_completed(self, before_run_id: int | None = None) -> Run | None:
        stmt = select(Run).where(Run.status == "completed")
        if before_run_id is not None:
            stmt = stmt.where(Run.id < before_run_id)
        return self.session.scalars(stmt.order_by(Run.id.desc())).first()

    def any_in_progress(self) -> Run | None:
        return self.session.scalars(
            select(Run).where(Run.status.in_(("pending", "running"))).order_by(Run.id.desc())
        ).first()

    def record_timing(self, run_id: int, stage: str, seconds: float) -> None:
        run = self.session.get(Run, run_id)
        if run is None:
            raise ValueError(f"Unknown run {run_id}")
        timings = dict(run.stage_timings or {})
        timings[stage] = round(seconds, 3)
        run.stage_timings = timings
        self.session.flush()

    def set_stage(self, run_id: int, stage: str) -> None:
        run = self.session.get(Run, run_id)
        if run is None:
            raise ValueError(f"Unknown run {run_id}")
        run.stage = stage
        run.status = "running"
        self.session.flush()

    def finish(self, run_id: int, *, error: str | None = None) -> None:
        run = self.session.get(Run, run_id)
        if run is None:
            raise ValueError(f"Unknown run {run_id}")
        run.status = "failed" if error else "completed"
        if error:
            run.error = error
        run.finished_at = datetime.utcnow()
        self.session.flush()

    def append_error(self, run_id: int, message: str) -> None:
        """Record a non-fatal per-competitor failure without aborting the run."""
        run = self.session.get(Run, run_id)
        if run is None:
            raise ValueError(f"Unknown run {run_id}")
        run.error = f"{run.error}\n{message}" if run.error else message
        self.session.flush()


class ProfileRepo:
    def __init__(self, session: Session) -> None:
        self.session = session

    def upsert(self, competitor_id: int, profile: CompanyProfileIn) -> CompanyProfile:
        """One profile row per competitor; a re-collect overwrites it in place."""
        existing = self.session.scalar(
            select(CompanyProfile).where(CompanyProfile.competitor_id == competitor_id)
        )
        fields = dict(
            description=profile.description,
            followers=profile.followers,
            geographies=profile.geographies,
            services=profile.services,
            target_audience=profile.target_audience,
            positioning=profile.positioning,
            fetched_at=datetime.utcnow(),
        )
        if existing:
            for key, value in fields.items():
                setattr(existing, key, value)
            self.session.flush()
            return existing
        row = CompanyProfile(competitor_id=competitor_id, **fields)
        self.session.add(row)
        self.session.flush()
        return row

    def get(self, competitor_id: int) -> CompanyProfile | None:
        return self.session.scalar(
            select(CompanyProfile).where(CompanyProfile.competitor_id == competitor_id)
        )


class PostRepo:
    def __init__(self, session: Session) -> None:
        self.session = session

    def insert_new(
        self,
        *,
        run_id: int,
        competitor_id: int,
        posts: list[RawPost],
        source_adapter: str,
    ) -> list[Post]:
        """Insert posts whose URL is not already stored. Dedup is global on URL."""
        if not posts:
            return []
        incoming = {p.url for p in posts}
        already = set(self.session.scalars(select(Post.url).where(Post.url.in_(incoming))).all())
        created: list[Post] = []
        for post in posts:
            if post.url in already:
                continue
            already.add(post.url)  # guard against dupes within this batch
            row = Post(
                competitor_id=competitor_id,
                run_id=run_id,
                url=post.url,
                posted_at=post.posted_at,
                content=post.content,
                raw_format=post.media_type,
                reactions=post.reactions,
                comments=post.comments,
                reposts=post.reposts,
                hashtags=post.hashtags,
                source_adapter=source_adapter,
            )
            self.session.add(row)
            created.append(row)
        self.session.flush()
        return created

    def list_for_competitor(self, competitor_id: int) -> list[Post]:
        return list(
            self.session.scalars(
                select(Post).where(Post.competitor_id == competitor_id).order_by(Post.posted_at)
            )
        )

    def count_for_run(self, run_id: int) -> int:
        return (
            self.session.scalar(select(func.count()).select_from(Post).where(Post.run_id == run_id))
            or 0
        )

    def count_all(self) -> int:
        return self.session.scalar(select(func.count()).select_from(Post)) or 0


class PostIntelligenceRepo:
    """Derived per-post classification, keyed by ``post_id``; raw posts stay immutable.

    Caching is prompt-version aware: a row is stale when its stored ``prompt_versions``
    no longer matches the current registry versions, which forces reprocessing.
    """

    def __init__(self, session: Session) -> None:
        self.session = session

    def _row_for_post(self, post_id: int) -> PostIntelligence | None:
        return self.session.scalar(
            select(PostIntelligence).where(PostIntelligence.post_id == post_id)
        )

    def unclassified(self, run_id: int, prompt_versions: dict[str, int]) -> list[Post]:
        """Posts in the run with no intelligence row, or a row from stale prompt versions."""
        posts = list(
            self.session.scalars(select(Post).where(Post.run_id == run_id).order_by(Post.id))
        )
        stale: list[Post] = []
        for post in posts:
            row = self._row_for_post(post.id)
            if row is None or (row.prompt_versions or {}) != prompt_versions:
                stale.append(post)
        return stale

    def upsert(
        self,
        post_id: int,
        classification: PostClassification,
        *,
        hashtags: list[str],
        prompt_versions: dict[str, int],
    ) -> PostIntelligence:
        fields = dict(
            format=classification.format,
            topic=classification.topic,
            sub_topic=classification.sub_topic,
            cta=classification.cta,
            cta_text=classification.cta_text,
            hashtags=list(hashtags),
            keywords=[tag.model_dump() for tag in classification.keywords],
            prompt_versions=dict(prompt_versions),
        )
        existing = self._row_for_post(post_id)
        if existing:
            for key, value in fields.items():
                setattr(existing, key, value)
            self.session.flush()
            return existing
        row = PostIntelligence(post_id=post_id, **fields)
        self.session.add(row)
        self.session.flush()
        return row

    def get(self, post_id: int) -> PostIntelligence | None:
        return self._row_for_post(post_id)

    def list_for_run(self, run_id: int) -> list[PostIntelligence]:
        return list(
            self.session.scalars(
                select(PostIntelligence)
                .join(Post, Post.id == PostIntelligence.post_id)
                .where(Post.run_id == run_id)
                .order_by(PostIntelligence.post_id)
            )
        )

    def count_for_run(self, run_id: int) -> int:
        return (
            self.session.scalar(
                select(func.count())
                .select_from(PostIntelligence)
                .join(Post, Post.id == PostIntelligence.post_id)
                .where(Post.run_id == run_id)
            )
            or 0
        )


def _avg(values: list[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def _avg_or_none(values: list[float]) -> float | None:
    return sum(values) / len(values) if values else None


class AnalysisRepo:
    """Engagement scoring write-back plus every ranking query (brief steps 4-5).

    Rankings are computed in Python over one indexed fetch of the run's scored posts —
    deterministic, no LLM, and trivially unit-testable against a hand-computed fixture.
    """

    def __init__(self, session: Session) -> None:
        self.session = session

    # ---- scoring write-back ------------------------------------------------ #
    def metrics_for_run(self, run_id: int):
        """Raw metrics + follower count for every classified post in the run."""
        stmt = (
            select(
                Post.id.label("post_id"),
                Post.reactions.label("reactions"),
                Post.comments.label("comments"),
                Post.reposts.label("reposts"),
                CompanyProfile.followers.label("followers"),
            )
            .join(PostIntelligence, PostIntelligence.post_id == Post.id)
            .outerjoin(CompanyProfile, CompanyProfile.competitor_id == Post.competitor_id)
            .where(Post.run_id == run_id)
            .order_by(Post.id)
        )
        return list(self.session.execute(stmt))

    def set_post_scores(self, scores: dict) -> None:
        """``scores``: ``{post_id: PostScore}``. Writes score/rate/metrics_complete."""
        if not scores:
            return
        rows = self.session.scalars(
            select(PostIntelligence).where(PostIntelligence.post_id.in_(list(scores)))
        ).all()
        for row in rows:
            score = scores[row.post_id]
            row.engagement_score = score.engagement_score
            row.engagement_rate = score.engagement_rate
            row.metrics_complete = score.metrics_complete
        self.session.flush()

    # ---- shared fetch ---------------------------------------------------- #
    def scored_rows_for_run(self, run_id: int):
        """One row per classified post: identity + classification + engagement."""
        stmt = (
            select(
                Post.id.label("post_id"),
                Post.competitor_id.label("competitor_id"),
                Competitor.name.label("competitor_name"),
                Post.url.label("url"),
                Post.posted_at.label("posted_at"),
                Post.hashtags.label("hashtags"),
                PostIntelligence.format.label("format"),
                PostIntelligence.topic.label("topic"),
                PostIntelligence.sub_topic.label("sub_topic"),
                PostIntelligence.cta.label("cta"),
                PostIntelligence.keywords.label("keywords"),
                PostIntelligence.engagement_score.label("engagement_score"),
                PostIntelligence.engagement_rate.label("engagement_rate"),
                PostIntelligence.metrics_complete.label("metrics_complete"),
            )
            .join(PostIntelligence, PostIntelligence.post_id == Post.id)
            .join(Competitor, Competitor.id == Post.competitor_id)
            .where(Post.run_id == run_id)
            .order_by(Post.id)
        )
        return list(self.session.execute(stmt))

    # ---- rankings ------------------------------------------------------- #
    @staticmethod
    def _to_top_post(row) -> TopPost:
        return TopPost(
            post_id=row.post_id,
            competitor_id=row.competitor_id,
            competitor_name=row.competitor_name,
            url=row.url,
            posted_at=row.posted_at,
            format=row.format,
            topic=row.topic,
            engagement_score=row.engagement_score or 0.0,
            engagement_rate=row.engagement_rate,
            metrics_complete=bool(row.metrics_complete),
        )

    @staticmethod
    def _rank_key(row):
        # highest score first; stable tie-break on post_id so results are deterministic
        return (-(row.engagement_score or 0.0), row.post_id)

    def top_posts(self, run_id: int, n: int) -> list[TopPost]:
        rows = sorted(self.scored_rows_for_run(run_id), key=self._rank_key)
        return [self._to_top_post(r) for r in rows[: max(0, n)]]

    def top_posts_by_competitor(self, run_id: int, n: int) -> list[CompetitorTopPosts]:
        by_competitor: dict[int, list] = defaultdict(list)
        names: dict[int, str] = {}
        for row in self.scored_rows_for_run(run_id):
            by_competitor[row.competitor_id].append(row)
            names[row.competitor_id] = row.competitor_name
        out: list[CompetitorTopPosts] = []
        for competitor_id in sorted(by_competitor):
            ranked = sorted(by_competitor[competitor_id], key=self._rank_key)[: max(0, n)]
            out.append(
                CompetitorTopPosts(
                    competitor_id=competitor_id,
                    competitor_name=names[competitor_id],
                    posts=[self._to_top_post(r) for r in ranked],
                )
            )
        return out

    def _group_performance(self, run_id: int, attr: str):
        groups: dict[str, list] = defaultdict(list)
        for row in self.scored_rows_for_run(run_id):
            key = getattr(row, attr)
            if key is None:
                continue
            groups[key].append(row)
        summary: dict[str, dict] = {}
        for key, rows in groups.items():
            best = min(rows, key=self._rank_key)
            summary[key] = dict(
                posts=len(rows),
                avg_engagement=_avg([r.engagement_score or 0.0 for r in rows]),
                avg_rate=_avg_or_none(
                    [r.engagement_rate for r in rows if r.engagement_rate is not None]
                ),
                best_post=best.url,
                best_post_score=best.engagement_score or 0.0,
            )
        return summary

    def top_formats(self, run_id: int) -> list[FormatPerformance]:
        rows = [
            FormatPerformance(format=key, **vals)
            for key, vals in self._group_performance(run_id, "format").items()
        ]
        return sorted(rows, key=lambda r: (-r.avg_engagement, r.format))

    def top_topics(self, run_id: int) -> list[TopicPerformance]:
        rows = [
            TopicPerformance(topic=key, **vals)
            for key, vals in self._group_performance(run_id, "topic").items()
        ]
        return sorted(rows, key=lambda r: (-r.avg_engagement, r.topic))

    def top_ctas(self, run_id: int) -> list[CtaPerformance]:
        rows = [
            CtaPerformance(cta=key, **vals)
            for key, vals in self._group_performance(run_id, "cta").items()
        ]
        return sorted(rows, key=lambda r: (-r.avg_engagement, r.cta))


class CampaignRepo:
    """Derived campaign records, keyed by ``run_id``. A re-run replaces the run's set."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def replace_for_run(self, run_id: int, campaigns: list[ValidatedCampaign]) -> list[Campaign]:
        for existing in self.session.scalars(select(Campaign).where(Campaign.run_id == run_id)):
            self.session.delete(existing)
        self.session.flush()
        created: list[Campaign] = []
        for campaign in campaigns:
            row = Campaign(
                competitor_id=campaign.competitor_id,
                run_id=run_id,
                name=campaign.name,
                theme=campaign.theme,
                objective=campaign.objective,
                post_ids=list(campaign.post_ids),
                start_date=campaign.start_date,
                end_date=campaign.end_date,
                formats=list(campaign.formats),
                keywords=list(campaign.keywords),
                hashtags=list(campaign.hashtags),
                cta=campaign.dominant_cta,
                target_audience=campaign.target_audience,
                total_engagement=campaign.total_engagement,
                top_post_id=campaign.top_post_id,
                performance_summary=campaign.performance_summary,
            )
            self.session.add(row)
            created.append(row)
        self.session.flush()
        return created

    def list_for_run(self, run_id: int) -> list[Campaign]:
        return list(
            self.session.scalars(
                select(Campaign).where(Campaign.run_id == run_id).order_by(Campaign.id)
            )
        )

    def count_for_run(self, run_id: int) -> int:
        return (
            self.session.scalar(
                select(func.count()).select_from(Campaign).where(Campaign.run_id == run_id)
            )
            or 0
        )


class StrategyProfileRepo:
    """Per-competitor strategy profiles (EPIC-05), keyed by run. A re-run replaces the set."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def replace_for_run(self, run_id: int, profiles) -> list[StrategyProfileRow]:
        """``profiles``: iterable of :class:`app.schemas.strategy_map.StrategyProfile`."""
        for existing in self.session.scalars(
            select(StrategyProfileRow).where(StrategyProfileRow.run_id == run_id)
        ):
            self.session.delete(existing)
        self.session.flush()
        created: list[StrategyProfileRow] = []
        for profile in profiles:
            row = StrategyProfileRow(
                competitor_id=profile.competitor_id,
                run_id=run_id,
                primary_themes=list(profile.primary_themes),
                content_mix=dict(profile.content_mix),
                best_format=profile.best_format,
                best_topic=profile.best_topic,
                posting_frequency_per_week=profile.posting_frequency_per_week,
                engagement_windows=list(profile.engagement_windows),
                positioning_summary=profile.positioning_summary,
            )
            self.session.add(row)
            created.append(row)
        self.session.flush()
        return created

    def list_for_run(self, run_id: int) -> list[StrategyProfileRow]:
        return list(
            self.session.scalars(
                select(StrategyProfileRow)
                .where(StrategyProfileRow.run_id == run_id)
                .order_by(StrategyProfileRow.competitor_id)
            )
        )

    def count_for_run(self, run_id: int) -> int:
        return (
            self.session.scalar(
                select(func.count())
                .select_from(StrategyProfileRow)
                .where(StrategyProfileRow.run_id == run_id)
            )
            or 0
        )


class InsightRepo:
    """Run-keyed derived insight bundles (``insights`` table).

    ``kind`` is one of: cross_competitor | top_content | strategy | opportunities |
    calendar | period_diff | change_report. One row per (run, kind); writing replaces it.
    """

    def __init__(self, session: Session) -> None:
        self.session = session

    def put(self, run_id: int, kind: str, payload) -> Insight:
        existing = self.session.scalar(
            select(Insight).where(Insight.run_id == run_id, Insight.kind == kind)
        )
        if existing:
            existing.payload = payload
            existing.created_at = datetime.utcnow()
            self.session.flush()
            return existing
        row = Insight(run_id=run_id, kind=kind, payload=payload)
        self.session.add(row)
        self.session.flush()
        return row

    def get(self, run_id: int, kind: str) -> Insight | None:
        return self.session.scalar(
            select(Insight).where(Insight.run_id == run_id, Insight.kind == kind)
        )

    def get_payload(self, run_id: int, kind: str):
        row = self.get(run_id, kind)
        return row.payload if row is not None else None

    def list_for_run(self, run_id: int) -> list[Insight]:
        return list(
            self.session.scalars(
                select(Insight).where(Insight.run_id == run_id).order_by(Insight.kind)
            )
        )
