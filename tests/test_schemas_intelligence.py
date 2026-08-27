import pytest
from pydantic import ValidationError

from app.config.settings import get_taxonomies
from app.schemas import SCHEMA_REGISTRY
from app.schemas.intelligence import (
    BatchClassification,
    FormatClassification,
    KeywordTag,
    PostClassification,
)


def test_all_intelligence_schemas_registered():
    for name in (
        "FormatClassification",
        "TopicClassification",
        "CtaClassification",
        "KeywordClassification",
        "PostClassification",
        "BatchClassification",
        "KeywordTag",
    ):
        assert name in SCHEMA_REGISTRY


def test_format_value_must_be_in_taxonomy():
    tax = get_taxonomies()
    ok = FormatClassification.model_validate({"results": [{"index": 0, "format": tax.formats[0]}]})
    assert ok.results[0].format == tax.formats[0]
    with pytest.raises(ValidationError):
        FormatClassification.model_validate({"results": [{"index": 0, "format": "not_a_format"}]})


def test_keyword_tag_normalizes_and_validates_category():
    tag = KeywordTag(term="  Zero Trust  ", category="industry_term")
    assert tag.term == "zero trust"
    assert tag.source == "llm"
    with pytest.raises(ValidationError):
        KeywordTag(term="x", category="made_up_category")
    with pytest.raises(ValidationError):
        KeywordTag(term="x", category="frequent", source="guess")


def test_post_classification_roundtrip():
    tax = get_taxonomies()
    pc = PostClassification(
        index=0,
        format=tax.formats[1],
        topic=tax.topics[0],
        sub_topic="edge inference",
        cta="download",
        cta_text="Get the guide",
        keywords=[KeywordTag(term="foo", category="frequent", source="tfidf")],
    )
    batch = BatchClassification(results=[pc])
    assert batch.results[0].keywords[0].source == "tfidf"
