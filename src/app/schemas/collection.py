"""Data contracts for the input & collection layer (EPIC-02).

- ``CompetitorIn`` / ``RowError`` / ``IngestReport`` — Excel ingest results.
- ``CompanyProfile`` / ``RawPost`` — what every ``DataSource`` adapter returns.

These are inter-layer contracts (Pydantic v2). Raw posts are immutable once collected;
analysis writes only to derived tables keyed by ``run_id``.
"""

from __future__ import annotations

import re
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator

HASHTAG_RE = re.compile(r"#(\w+)")

MEDIA_TYPES = (
    "image",
    "carousel",
    "video",
    "text",
    "poll",
    "article",
    "document",
    "unknown",
)
MediaType = Literal["image", "carousel", "video", "text", "poll", "article", "document", "unknown"]

PRIORITIES = ("High", "Medium", "Low")


def parse_hashtags(text: str) -> list[str]:
    """Extract ``#tag`` tokens from free text, order-preserving and de-duplicated."""
    seen: dict[str, None] = {}
    for match in HASHTAG_RE.findall(text or ""):
        seen.setdefault(match.lower(), None)
    return list(seen)


# --------------------------------------------------------------------------- #
# Excel ingest
# --------------------------------------------------------------------------- #
class CompetitorIn(BaseModel):
    """One validated competitor row, ready to upsert into ``competitors``."""

    name: str
    linkedin_url: str  # canonical https://www.linkedin.com/company/<slug>
    industry: str | None = None
    market: str | None = None
    priority: str = "Medium"

    @field_validator("priority")
    @classmethod
    def _known_priority(cls, v: str) -> str:
        if v not in PRIORITIES:
            raise ValueError(f"priority must be one of {PRIORITIES}")
        return v


class RowError(BaseModel):
    """A rejected spreadsheet row with the reason it was dropped."""

    row: int  # 1-based row number as seen in the sheet (header = row 1)
    reason: str
    data: dict = Field(default_factory=dict)


class IngestReport(BaseModel):
    accepted: list[CompetitorIn] = Field(default_factory=list)
    rejected: list[RowError] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)

    @property
    def accepted_count(self) -> int:
        return len(self.accepted)

    @property
    def rejected_count(self) -> int:
        return len(self.rejected)


# --------------------------------------------------------------------------- #
# Adapter output
# --------------------------------------------------------------------------- #
class CompanyProfile(BaseModel):
    name: str | None = None
    linkedin_url: str | None = None
    description: str | None = None
    industry: str | None = None
    website: str | None = None
    followers: int | None = None
    geographies: list[str] = Field(default_factory=list)
    services: list[str] = Field(default_factory=list)
    target_audience: str | None = None
    positioning: str | None = None


class RawPost(BaseModel):
    url: str
    posted_at: datetime
    content: str
    media_type: MediaType = "unknown"
    reactions: int | None = None
    comments: int | None = None
    reposts: int | None = None
    hashtags: list[str] = Field(default_factory=list)

    @field_validator("media_type", mode="before")
    @classmethod
    def _coerce_media_type(cls, v: object) -> str:
        if v is None:
            return "unknown"
        s = str(v).strip().lower()
        return s if s in MEDIA_TYPES else "unknown"

    @model_validator(mode="after")
    def _normalize_hashtags(self) -> RawPost:
        if self.hashtags:
            self.hashtags = [
                h.lstrip("#").strip().lower() for h in self.hashtags if h and h.strip()
            ]
        else:
            self.hashtags = parse_hashtags(self.content)
        return self
