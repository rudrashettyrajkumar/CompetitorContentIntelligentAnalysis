"""Data contracts for the AI strategy layer (EPIC-06).

The deep agent proposes; Python validates and stamps. Three validated outputs —
``ContentStrategy`` (pillars + mix + formats + cadence), ``ContentOpportunity`` list,
and ``ContentCalendar`` — plus the batched ``OriginalityVerdict`` schema for the LLM
similarity judge. The three ``*_signal`` / ``*_level`` / ``*_potential`` fields on
``ContentOpportunity`` are enums the LLM may fill but the derivation rules overwrite from
data, so they are always auditable.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from app.schemas import register_schema

Level = Literal["high", "medium", "low"]


# --------------------------------------------------------------------------- #
# content strategy (pillars / mix / formats / cadence)
# --------------------------------------------------------------------------- #


@register_schema
class Pillar(BaseModel):
    name: str
    description: str
    rationale: str  # cites which competitor signal / white space it answers


@register_schema
class FormatRec(BaseModel):
    format: str
    share: float  # percent of content in this format
    rationale: str


@register_schema
class ContentStrategy(BaseModel):
    pillars: list[Pillar] = Field(default_factory=list)
    content_mix: dict[str, float] = Field(default_factory=dict)  # category -> %, sums to 100
    recommended_formats: list[FormatRec] = Field(default_factory=list)
    posting_cadence: str = ""
    engagement_windows: list[str] = Field(default_factory=list)


# --------------------------------------------------------------------------- #
# content opportunities
# --------------------------------------------------------------------------- #


@register_schema
class ContentOpportunity(BaseModel):
    topic: str
    pillar: str
    competitor_signal: Level = "medium"
    competition_level: Level = "medium"
    engagement_potential: Level = "medium"
    recommended_format: str
    target_audience: str
    hook: str
    angle: str
    key_message: str
    structure: list[str] = Field(default_factory=list)
    cta: str
    keywords: list[str] = Field(default_factory=list)
    hashtags: list[str] = Field(default_factory=list)


@register_schema
class ContentOpportunityList(BaseModel):
    opportunities: list[ContentOpportunity] = Field(default_factory=list)


# --------------------------------------------------------------------------- #
# 30-day calendar
# --------------------------------------------------------------------------- #


@register_schema
class CalendarEntry(BaseModel):
    day: int = Field(ge=1)
    weekday: str
    pillar: str
    topic: str
    format: str
    objective: str
    cta: str
    opportunity_ref: int | None = None  # index into the opportunities list


@register_schema
class ContentCalendar(BaseModel):
    entries: list[CalendarEntry] = Field(default_factory=list)
    cadence_note: str = ""


# --------------------------------------------------------------------------- #
# originality guard
# --------------------------------------------------------------------------- #


@register_schema
class OriginalityVerdictItem(BaseModel):
    index: int = Field(ge=0)
    is_rewrite: bool
    reason: str = ""


@register_schema
class OriginalityVerdict(BaseModel):
    results: list[OriginalityVerdictItem] = Field(default_factory=list)


@register_schema
class RegeneratedField(BaseModel):
    """LLM output when regenerating a single rejected hook / angle / key_message."""

    text: str


class OriginalityCheck(BaseModel):
    """One guard result kept alongside the strategy bundle for auditability."""

    field: str  # "hook" | "angle" | "key_message"
    opportunity_index: int
    text: str
    verdict: Literal["ok", "rejected_ngram", "rejected_llm", "regenerated", "dropped"]
    detail: str = ""
    overlap_ratio: float | None = None


class StrategyBundle(BaseModel):
    """Everything EPIC-06 produces for one run, as persisted / exported."""

    strategy: ContentStrategy
    opportunities: list[ContentOpportunity] = Field(default_factory=list)
    calendar: ContentCalendar
    originality_checks: list[OriginalityCheck] = Field(default_factory=list)
