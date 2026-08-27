from datetime import datetime

from app.schemas.collection import CompetitorIn, RawPost, parse_hashtags


def test_parse_hashtags_dedup_and_lowercase():
    assert parse_hashtags("Growth #AI and #ai plus #DataOps") == ["ai", "dataops"]


def test_rawpost_parses_hashtags_from_content_when_absent():
    post = RawPost(
        url="u1",
        posted_at=datetime(2026, 1, 1),
        content="Big news #ProductLaunch #Innovation",
    )
    assert post.hashtags == ["productlaunch", "innovation"]
    assert post.media_type == "unknown"


def test_rawpost_keeps_explicit_hashtags():
    post = RawPost(
        url="u1",
        posted_at=datetime(2026, 1, 1),
        content="text #ignored",
        hashtags=["kept"],
    )
    assert post.hashtags == ["kept"]


def test_rawpost_unknown_media_type_coerced():
    post = RawPost(url="u", posted_at=datetime(2026, 1, 1), content="x", media_type="LiveVideo")
    assert post.media_type == "unknown"


def test_competitor_in_defaults_priority_medium():
    c = CompetitorIn(name="A", linkedin_url="https://www.linkedin.com/company/a")
    assert c.priority == "Medium"
