"""Data contracts for the engagement & campaign layer (EPIC-04).

Two families:

* **Ranking result models** — plain Pydantic returned by ``AnalysisRepo`` queries. No
  LLM involved; shapes mirror brief step 5 (Format | Posts | Avg engagement | Best post).
* **Campaign models** — ``CampaignRecord`` is the deep agent's *untrusted* output schema;
  ``ValidatedCampaign`` is what survives deterministic Python validation and is persisted
  to ``campaigns``.
"""

from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel, Field

from app.schemas import register_schema

# --------------------------------------------------------------------------- #
# ranking result models (pure query output — no LLM)
# --------------------------------------------------------------------------- #


class TopPost(BaseModel):
    post_id: int
    competitor_id: int
    competitor_name: str
    url: str
    posted_at: datetime
    format: str | None = None
    topic: str | None = None
    engagement_score: float
    engagement_rate: float | None = None
    metrics_complete: bool = True


class CompetitorTopPosts(BaseModel):
    competitor_id: int
    competitor_name: str
    posts: list[TopPost] = Field(default_factory=list)


class _PerformanceRow(BaseModel):
    posts: int
    avg_engagement: float
    avg_rate: float | None = None
    best_post: str | None = None  # URL of the highest-scoring post in the group
    best_post_score: float | None = None


class FormatPerformance(_PerformanceRow):
    format: str


class TopicPerformance(_PerformanceRow):
    topic: str


class CtaPerformance(_PerformanceRow):
    cta: str


# --------------------------------------------------------------------------- #
# campaign detection
# --------------------------------------------------------------------------- #


@register_schema
class CampaignRecord(BaseModel):
    """One campaign as proposed by the deep agent. Never persisted as-is — every field is
    re-checked (URLs, competitor ownership, window, aggregates) before it becomes a
    :class:`ValidatedCampaign`."""

    name: str
    theme: str
    objective: str | None = None
    post_urls: list[str] = Field(default_factory=list)
    start_date: date | None = None
    end_date: date | None = None
    formats: list[str] = Field(default_factory=list)
    keywords: list[str] = Field(default_factory=list)
    hashtags: list[str] = Field(default_factory=list)
    dominant_cta: str | None = None
    inferred_target_audience: str | None = None
    total_engagement: float = 0.0
    top_post_url: str | None = None
    performance_summary: str | None = None


@register_schema
class CampaignClustering(BaseModel):
    """Batch wrapper: the agent returns every campaign it found for one competitor."""

    campaigns: list[CampaignRecord] = Field(default_factory=list)


class ValidatedCampaign(BaseModel):
    """A campaign that passed deterministic validation. Aggregates are recomputed from the
    member posts, not taken from the agent."""

    competitor_id: int
    name: str
    theme: str
    objective: str | None = None
    post_ids: list[int]
    post_urls: list[str]
    start_date: datetime
    end_date: datetime
    formats: list[str] = Field(default_factory=list)
    keywords: list[str] = Field(default_factory=list)
    hashtags: list[str] = Field(default_factory=list)
    dominant_cta: str | None = None
    target_audience: str | None = None
    total_engagement: float = 0.0
    top_post_id: int | None = None
    top_post_url: str | None = None
    performance_summary: str | None = None
