"""Data contracts for the intelligence layer (EPIC-03).

Four batched LLM tasks — format, topic, CTA, keyword — each with its own registered
output schema, plus the merged ``PostClassification`` that is persisted to
``post_intelligence``. Taxonomy fields validate against ``config/taxonomies.yaml`` so a
free model that invents a value is rejected and the router's repair round-trip fires.
"""

from __future__ import annotations

from pydantic import BaseModel, Field, field_validator

from app.config.settings import get_taxonomies
from app.schemas import register_schema


def _in_taxonomy(value: str, allowed: list[str], field: str) -> str:
    if value not in allowed:
        raise ValueError(f"{field} {value!r} is not in the configured taxonomy {allowed}")
    return value


@register_schema
class KeywordTag(BaseModel):
    term: str
    category: str = "frequent"
    source: str = "llm"  # llm | tfidf

    @field_validator("term")
    @classmethod
    def _norm_term(cls, v: str) -> str:
        v = v.strip().lower()
        if not v:
            raise ValueError("keyword term must not be empty")
        return v

    @field_validator("category")
    @classmethod
    def _known_category(cls, v: str) -> str:
        return _in_taxonomy(v, get_taxonomies().keyword_categories, "keyword category")

    @field_validator("source")
    @classmethod
    def _known_source(cls, v: str) -> str:
        if v not in ("llm", "tfidf"):
            raise ValueError("keyword source must be 'llm' or 'tfidf'")
        return v


# --------------------------------------------------------------------------- #
# per-task batch results (one LLM call classifies up to N posts)
# --------------------------------------------------------------------------- #
class _IndexedResult(BaseModel):
    index: int = Field(ge=0)  # position of the post within the batch


@register_schema
class FormatResult(_IndexedResult):
    format: str

    @field_validator("format")
    @classmethod
    def _known_format(cls, v: str) -> str:
        return _in_taxonomy(v, get_taxonomies().formats, "format")


@register_schema
class FormatClassification(BaseModel):
    results: list[FormatResult]


@register_schema
class TopicResult(_IndexedResult):
    topic: str
    sub_topic: str | None = None

    @field_validator("topic")
    @classmethod
    def _known_topic(cls, v: str) -> str:
        return _in_taxonomy(v, get_taxonomies().topics, "topic")


@register_schema
class TopicClassification(BaseModel):
    results: list[TopicResult]


@register_schema
class CtaResult(_IndexedResult):
    cta: str
    cta_text: str | None = None

    @field_validator("cta")
    @classmethod
    def _known_cta(cls, v: str) -> str:
        return _in_taxonomy(v, get_taxonomies().cta_types, "cta")


@register_schema
class CtaClassification(BaseModel):
    results: list[CtaResult]


@register_schema
class KeywordResult(_IndexedResult):
    keywords: list[KeywordTag] = Field(default_factory=list)


@register_schema
class KeywordClassification(BaseModel):
    results: list[KeywordResult]


# --------------------------------------------------------------------------- #
# merged per-post classification (persisted to post_intelligence)
# --------------------------------------------------------------------------- #
@register_schema
class PostClassification(BaseModel):
    index: int = Field(ge=0)
    format: str
    topic: str
    sub_topic: str | None = None
    cta: str
    cta_text: str | None = None
    keywords: list[KeywordTag] = Field(default_factory=list)

    @field_validator("format")
    @classmethod
    def _fmt(cls, v: str) -> str:
        return _in_taxonomy(v, get_taxonomies().formats, "format")

    @field_validator("topic")
    @classmethod
    def _top(cls, v: str) -> str:
        return _in_taxonomy(v, get_taxonomies().topics, "topic")

    @field_validator("cta")
    @classmethod
    def _cta(cls, v: str) -> str:
        return _in_taxonomy(v, get_taxonomies().cta_types, "cta")


@register_schema
class BatchClassification(BaseModel):
    results: list[PostClassification]
