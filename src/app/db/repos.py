"""Repositories own every query. Feature code never touches SQLAlchemy directly.

EPIC-01 ships CompetitorRepo and RunRepo; EPIC-02 adds ProfileRepo and PostRepo;
EPIC-03 adds PostIntelligenceRepo.
"""

from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.models import CompanyProfile, Competitor, Post, PostIntelligence, Run
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

    def create(self, *, period_days: int, adapter: str) -> Run:
        run = Run(period_days=period_days, adapter=adapter, status="pending")
        self.session.add(run)
        self.session.flush()
        return run

    def get(self, run_id: int) -> Run | None:
        return self.session.get(Run, run_id)

    def list_all(self) -> list[Run]:
        return list(self.session.scalars(select(Run).order_by(Run.started_at.desc())))

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
