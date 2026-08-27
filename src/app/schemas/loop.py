"""Data contracts for the continuous intelligence loop (EPIC-08).

``PeriodDiff`` is pure computation over two completed runs; ``ChangeReport`` is the
single LLM touch (a short executive narrative). Both persist to ``insights`` — kinds
``period_diff`` and ``change_report``.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from app.schemas import register_schema


class KeywordDelta(BaseModel):
    term: str
    before: int
    after: int
    growth: float  # after / max(before, 1)  (or before/after for fading)


class TopicShift(BaseModel):
    topic: str
    before: float
    after: float
    delta: float  # after - before (avg engagement)
    pct: float  # delta / max(|before|, 1)


class FormatShift(BaseModel):
    format: str
    before: float
    after: float
    delta: float
    pct: float


class ProfileChange(BaseModel):
    competitor: str
    field: str  # cadence | best_format | dominant_mix
    before: str
    after: str


class PeriodDiff(BaseModel):
    baseline_run_id: int
    current_run_id: int
    new_posts: int
    posts_delta_pct: float
    new_campaigns: list[str] = Field(default_factory=list)
    ended_campaigns: list[str] = Field(default_factory=list)
    emerging_keywords: list[KeywordDelta] = Field(default_factory=list)
    fading_keywords: list[KeywordDelta] = Field(default_factory=list)
    topic_performance_shifts: list[TopicShift] = Field(default_factory=list)
    format_shifts: list[FormatShift] = Field(default_factory=list)
    profile_changes: list[ProfileChange] = Field(default_factory=list)
    strategy_refresh_recommended: bool = False
    refresh_reasons: list[str] = Field(default_factory=list)

    def material_change_count(self) -> int:
        return (
            len(self.new_campaigns)
            + len(self.ended_campaigns)
            + len(self.emerging_keywords)
            + len(self.fading_keywords)
            + len(self.topic_performance_shifts)
            + len(self.format_shifts)
            + len(self.profile_changes)
        )


@register_schema
class ChangeReport(BaseModel):
    """LLM output: a short 'what changed, what to do' narrative for the dashboard."""

    narrative: str
    headline: str = ""
