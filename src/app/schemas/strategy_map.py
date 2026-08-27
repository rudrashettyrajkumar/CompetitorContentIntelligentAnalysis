"""Data contracts for competitor strategy mapping & cross-competitor intelligence (EPIC-05).

Three families:

* **Strategy profiles** — one per competitor, computed with pandas over the DB. Only the
  ``positioning_summary`` is LLM-authored (``PositioningSummary`` is that call's schema).
* **Cross-competitor insights** — pure computation over the run's scored posts: common /
  saturated themes, white spaces, opportunity topics, format opportunities, and the
  frequency-vs-performance keyword matrix.
* **Top content report** — Top-N posts across competitors, each with an LLM
  ``WhyItWorked`` breakdown (``WhyItWorkedBatch`` is the batched call's schema).
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from app.schemas import register_schema

# --------------------------------------------------------------------------- #
# strategy profiles
# --------------------------------------------------------------------------- #


@register_schema
class PositioningSummary(BaseModel):
    """LLM output: a 2-3 sentence read on how the competitor positions itself."""

    summary: str


class StrategyProfile(BaseModel):
    competitor: str
    competitor_id: int
    primary_themes: list[str] = Field(default_factory=list)
    content_mix: dict[str, float] = Field(default_factory=dict)  # format-group -> %
    best_format: str | None = None
    best_topic: str | None = None
    posting_frequency_per_week: float = 0.0
    engagement_windows: list[str] = Field(default_factory=list)  # weekday abbrevs
    positioning_summary: str = ""


# --------------------------------------------------------------------------- #
# cross-competitor insights
# --------------------------------------------------------------------------- #


class ThemeStat(BaseModel):
    topic: str
    competitors_covering: int
    post_share: float  # fraction of all classified posts on this topic (0..1)
    avg_engagement: float = 0.0


class WhiteSpace(BaseModel):
    topic: str
    reason: Literal["low_coverage", "high_engagement_low_frequency"]
    competitors_covering: int
    post_share: float
    avg_engagement: float


class OpportunityTopic(BaseModel):
    topic: str
    avg_engagement: float
    post_share: float
    engagement_vs_median: float  # avg_engagement - median topic engagement
    coverage_vs_median: float  # post_share - median topic share


class FormatOpportunity(BaseModel):
    format: str
    post_share: float
    avg_engagement: float
    overall_avg_engagement: float
    engagement_multiplier: float  # avg_engagement / overall_avg_engagement


Quadrant = Literal[
    "high_freq_high_perf",
    "high_freq_low_perf",
    "low_freq_high_perf",
    "low_freq_low_perf",
]


class KeywordPerf(BaseModel):
    term: str
    frequency: int  # posts containing the term
    avg_engagement: float
    quadrant: Quadrant


class CrossCompetitorInsights(BaseModel):
    common_themes: list[ThemeStat] = Field(default_factory=list)
    saturated_topics: list[ThemeStat] = Field(default_factory=list)
    white_spaces: list[WhiteSpace] = Field(default_factory=list)
    opportunity_topics: list[OpportunityTopic] = Field(default_factory=list)
    format_opportunities: list[FormatOpportunity] = Field(default_factory=list)
    keyword_matrix: list[KeywordPerf] = Field(default_factory=list)


# --------------------------------------------------------------------------- #
# top content report
# --------------------------------------------------------------------------- #


@register_schema
class WhyItWorked(BaseModel):
    hook: str
    structure: str
    emotional_trigger: str | None = None
    data_usage: str | None = None
    visual_format: str
    cta_assessment: str
    audience_relevance: str
    timing_note: str | None = None
    length_note: str
    storytelling: str | None = None
    summary: str  # one-line "why" for the table


@register_schema
class WhyItWorkedResult(WhyItWorked):
    index: int = Field(ge=0)


@register_schema
class WhyItWorkedBatch(BaseModel):
    results: list[WhyItWorkedResult] = Field(default_factory=list)


class TopContentItem(BaseModel):
    rank: int
    post_id: int
    competitor: str
    url: str
    posted_at: datetime
    format: str | None = None
    topic: str | None = None
    engagement_score: float
    engagement_rate: float | None = None
    ranked_by: Literal["engagement_rate", "engagement_score"]
    why: WhyItWorked


class TopContentReport(BaseModel):
    ranked_by: Literal["engagement_rate", "engagement_score"]
    items: list[TopContentItem] = Field(default_factory=list)
