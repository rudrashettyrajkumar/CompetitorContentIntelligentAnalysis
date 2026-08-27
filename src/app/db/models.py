"""All tables (solution-design §6). Later epics populate them; raw posts are immutable
once collected — analysis writes only to derived tables keyed by run_id."""

from datetime import datetime

from sqlalchemy import JSON, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class Competitor(Base):
    __tablename__ = "competitors"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    linkedin_url: Mapped[str] = mapped_column(String(500), unique=True)
    industry: Mapped[str | None] = mapped_column(String(200))
    market: Mapped[str | None] = mapped_column(String(200))
    priority: Mapped[str] = mapped_column(String(20), default="Medium")
    website: Mapped[str | None] = mapped_column(String(500))
    status: Mapped[str] = mapped_column(String(20), default="active")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class CompanyProfile(Base):
    __tablename__ = "company_profiles"

    id: Mapped[int] = mapped_column(primary_key=True)
    competitor_id: Mapped[int] = mapped_column(ForeignKey("competitors.id"))
    description: Mapped[str | None] = mapped_column(Text)
    followers: Mapped[int | None] = mapped_column(Integer)
    geographies: Mapped[list | None] = mapped_column(JSON)
    services: Mapped[list | None] = mapped_column(JSON)
    target_audience: Mapped[str | None] = mapped_column(Text)
    positioning: Mapped[str | None] = mapped_column(Text)
    fetched_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class Run(Base):
    __tablename__ = "runs"

    id: Mapped[int] = mapped_column(primary_key=True)
    started_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime)
    period_days: Mapped[int] = mapped_column(Integer, default=30)
    adapter: Mapped[str] = mapped_column(String(50), default="mock")
    # status: pending | running | completed | failed
    status: Mapped[str] = mapped_column(String(20), default="pending")
    stage: Mapped[str | None] = mapped_column(String(50))
    error: Mapped[str | None] = mapped_column(Text)


class Post(Base):
    __tablename__ = "posts"
    __table_args__ = (UniqueConstraint("url", name="uq_posts_url"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    competitor_id: Mapped[int] = mapped_column(ForeignKey("competitors.id"))
    run_id: Mapped[int] = mapped_column(ForeignKey("runs.id"))
    url: Mapped[str] = mapped_column(String(500))
    posted_at: Mapped[datetime] = mapped_column(DateTime)
    content: Mapped[str] = mapped_column(Text)
    raw_format: Mapped[str | None] = mapped_column(String(50))  # media type from the source
    reactions: Mapped[int | None] = mapped_column(Integer)
    comments: Mapped[int | None] = mapped_column(Integer)
    reposts: Mapped[int | None] = mapped_column(Integer)
    hashtags: Mapped[list | None] = mapped_column(JSON)
    source_adapter: Mapped[str] = mapped_column(String(50))


class PostIntelligence(Base):
    __tablename__ = "post_intelligence"
    __table_args__ = (UniqueConstraint("post_id", name="uq_post_intelligence_post"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    post_id: Mapped[int] = mapped_column(ForeignKey("posts.id"))
    format: Mapped[str | None] = mapped_column(String(50))
    topic: Mapped[str | None] = mapped_column(String(100))
    sub_topic: Mapped[str | None] = mapped_column(String(200))
    cta: Mapped[str | None] = mapped_column(String(50))
    cta_text: Mapped[str | None] = mapped_column(String(500))
    keywords: Mapped[list | None] = mapped_column(JSON)
    engagement_score: Mapped[float | None] = mapped_column(Float)
    engagement_rate: Mapped[float | None] = mapped_column(Float)
    metrics_complete: Mapped[bool | None] = mapped_column(default=None)
    prompt_versions: Mapped[dict | None] = mapped_column(JSON)


class Campaign(Base):
    __tablename__ = "campaigns"

    id: Mapped[int] = mapped_column(primary_key=True)
    competitor_id: Mapped[int] = mapped_column(ForeignKey("competitors.id"))
    run_id: Mapped[int] = mapped_column(ForeignKey("runs.id"))
    name: Mapped[str] = mapped_column(String(200))
    theme: Mapped[str | None] = mapped_column(Text)
    objective: Mapped[str | None] = mapped_column(Text)
    post_ids: Mapped[list | None] = mapped_column(JSON)
    start_date: Mapped[datetime | None] = mapped_column(DateTime)
    end_date: Mapped[datetime | None] = mapped_column(DateTime)
    formats: Mapped[list | None] = mapped_column(JSON)
    keywords: Mapped[list | None] = mapped_column(JSON)
    hashtags: Mapped[list | None] = mapped_column(JSON)
    cta: Mapped[str | None] = mapped_column(String(50))
    target_audience: Mapped[str | None] = mapped_column(Text)
    total_engagement: Mapped[float | None] = mapped_column(Float)
    top_post_id: Mapped[int | None] = mapped_column(ForeignKey("posts.id"))
    performance_summary: Mapped[str | None] = mapped_column(Text)


class StrategyProfile(Base):
    __tablename__ = "strategy_profiles"

    id: Mapped[int] = mapped_column(primary_key=True)
    competitor_id: Mapped[int] = mapped_column(ForeignKey("competitors.id"))
    run_id: Mapped[int] = mapped_column(ForeignKey("runs.id"))
    primary_themes: Mapped[list | None] = mapped_column(JSON)
    content_mix: Mapped[dict | None] = mapped_column(JSON)
    best_format: Mapped[str | None] = mapped_column(String(50))
    best_topic: Mapped[str | None] = mapped_column(String(100))
    posting_frequency_per_week: Mapped[float | None] = mapped_column(Float)
    engagement_windows: Mapped[list | None] = mapped_column(JSON)
    positioning_summary: Mapped[str | None] = mapped_column(Text)


class Insight(Base):
    __tablename__ = "insights"

    id: Mapped[int] = mapped_column(primary_key=True)
    run_id: Mapped[int] = mapped_column(ForeignKey("runs.id"))
    kind: Mapped[str] = mapped_column(String(50))
    # cross_competitor | top_content | strategy | opportunities | calendar | period_diff
    payload: Mapped[dict | list | None] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
