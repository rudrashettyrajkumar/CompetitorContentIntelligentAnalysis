from datetime import datetime

import pytest

from app.config.settings import AppConfig, Settings
from app.datasources.apify import ApifyAdapter, ApifyConfigError, ApifyError

URL = "https://www.linkedin.com/company/nimbus-analytics"

APP_CONFIG = AppConfig(
    collection={
        "apify": {
            "base_url": "https://api.apify.test/v2",
            "profile_actor": "acme/profile",
            "posts_actor": "acme/posts",
            "posts_limit": 50,
        }
    }
)


class _Resp:
    def __init__(self, payload, status_code=200):
        self._payload = payload
        self.status_code = status_code

    def json(self):
        return self._payload


class _FakeClient:
    """Records requests and replays queued responses by actor path."""

    def __init__(self, by_path):
        self.by_path = by_path
        self.calls = []

    def post(self, url, params=None, json=None):
        self.calls.append({"url": url, "params": params, "json": json})
        for key, resp in self.by_path.items():
            if key in url:
                return resp
        return _Resp([], 404)


def _adapter(client):
    return ApifyAdapter(
        settings=Settings(apify_token="tok", _env_file=None),
        app_config=APP_CONFIG,
        client=client,
    )


def test_missing_token_raises():
    with pytest.raises(ApifyConfigError, match="APIFY_TOKEN"):
        ApifyAdapter(settings=Settings(apify_token="", _env_file=None), app_config=APP_CONFIG)


def test_missing_actor_ids_raises():
    with pytest.raises(ApifyConfigError, match="profile_actor"):
        ApifyAdapter(
            settings=Settings(apify_token="tok", _env_file=None),
            app_config=AppConfig(collection={"apify": {}}),
        )


def test_fetch_company_profile_maps_fields():
    client = _FakeClient(
        {
            "acme~profile": _Resp(
                [
                    {
                        "name": "Nimbus Analytics",
                        "description": "Analytics platform",
                        "followerCount": 48200,
                        "website": "https://nimbus.example",
                        "locations": ["North America", "UK"],
                        "specialties": "analytics, dashboards",
                    }
                ]
            )
        }
    )
    profile = _adapter(client).fetch_company_profile(URL)
    assert profile.name == "Nimbus Analytics"
    assert profile.followers == 48200
    assert profile.geographies == ["North America", "UK"]
    assert profile.services == ["analytics", "dashboards"]
    assert client.calls[0]["params"] == {"token": "tok"}


def test_fetch_posts_maps_and_filters_by_since():
    client = _FakeClient(
        {
            "acme~posts": _Resp(
                [
                    {
                        "url": "https://li/new",
                        "postedAt": "2026-08-20T12:00:00Z",
                        "text": "Recent #Launch",
                        "type": "video",
                        "numLikes": 300,
                        "numComments": 20,
                        "numShares": 5,
                    },
                    {
                        "url": "https://li/old",
                        "postedAt": "2026-01-01T12:00:00Z",
                        "text": "Old news",
                        "type": "text",
                    },
                    {"url": "https://li/nodate", "text": "no timestamp"},
                ]
            )
        }
    )
    posts = _adapter(client).fetch_posts(URL, datetime(2026, 8, 1))
    assert [p.url for p in posts] == ["https://li/new"]
    assert posts[0].media_type == "video"
    assert posts[0].reactions == 300
    assert posts[0].posted_at.tzinfo is None


def test_http_error_raises_apify_error():
    client = _FakeClient({"acme~profile": _Resp({"error": "boom"}, status_code=500)})
    with pytest.raises(ApifyError, match="HTTP 500"):
        _adapter(client).fetch_company_profile(URL)
