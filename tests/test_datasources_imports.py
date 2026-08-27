import json
from datetime import datetime

import pytest

from app.datasources.imports import ImportAdapter, ImportDataError

URL = "https://www.linkedin.com/company/nimbus-analytics"
SLUG = "nimbus-analytics"


@pytest.fixture
def imports_dir(tmp_path):
    d = tmp_path / SLUG
    d.mkdir()
    (d / "profile.json").write_text(
        json.dumps(
            {
                "name": "Nimbus Analytics",
                "description": "Analytics for ops teams.",
                "followers": 48200,
                "geographies": "North America, United Kingdom",
                "services": ["platform licensing", "professional services"],
                "positioning": "Self-serve BI.",
            }
        )
    )
    return tmp_path


def test_profile_mapping(imports_dir):
    adapter = ImportAdapter(imports_dir=imports_dir)
    profile = adapter.fetch_company_profile(URL)
    assert profile.name == "Nimbus Analytics"
    assert profile.followers == 48200
    assert profile.geographies == ["North America", "United Kingdom"]
    assert profile.linkedin_url == URL


def test_posts_from_json(imports_dir):
    (imports_dir / SLUG / "posts.json").write_text(
        json.dumps(
            [
                {
                    "url": "https://li/1",
                    "posted_at": "2026-08-20T10:00:00",
                    "content": "Recent post #Analytics",
                    "media_type": "carousel",
                    "reactions": 100,
                    "comments": 9,
                },
                {
                    "url": "https://li/2",
                    "posted_at": "2026-01-01T10:00:00",
                    "content": "Old post",
                    "media_type": "text",
                },
            ]
        )
    )
    adapter = ImportAdapter(imports_dir=imports_dir)
    recent = adapter.fetch_posts(URL, datetime(2026, 8, 1))
    assert [p.url for p in recent] == ["https://li/1"]
    assert recent[0].media_type == "carousel"
    assert recent[0].hashtags == ["analytics"]


def test_posts_from_csv(imports_dir):
    (imports_dir / SLUG / "posts.csv").write_text(
        "url,posted_at,content,media_type,reactions,comments,reposts,hashtags\n"
        "https://li/9,2026-08-15T09:00:00,New guide is live,document,208,11,,Guide;Ops\n"
    )
    adapter = ImportAdapter(imports_dir=imports_dir)
    posts = adapter.fetch_posts(URL, datetime(2026, 8, 1))
    assert len(posts) == 1
    assert posts[0].media_type == "document"
    assert posts[0].reactions == 208
    assert posts[0].reposts is None
    assert posts[0].hashtags == ["guide", "ops"]


def test_missing_directory_raises(tmp_path):
    adapter = ImportAdapter(imports_dir=tmp_path)
    with pytest.raises(ImportDataError, match="No import directory"):
        adapter.fetch_company_profile(URL)


def test_missing_posts_file_raises(imports_dir):
    adapter = ImportAdapter(imports_dir=imports_dir)
    with pytest.raises(ImportDataError, match="posts.json/posts.csv"):
        adapter.fetch_posts(URL, datetime(2026, 1, 1))
