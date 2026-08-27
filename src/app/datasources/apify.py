"""Apify-backed data source.

Calls two Apify actors (a company-profile scraper and a company-posts scraper) via the
platform's ``run-sync-get-dataset-items`` REST endpoint. Actor IDs come from
``config/app.yaml`` (``apify.profile_actor`` / ``apify.posts_actor``); the token comes
from the ``APIFY_TOKEN`` env var.

Actor output shapes vary between actors, so mapping is defensive: several candidate
keys are tried for every field.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from app.config.settings import AppConfig, Settings, get_app_config, get_settings
from app.datasources.base import DataSource
from app.schemas.collection import CompanyProfile, RawPost

_DEFAULT_BASE_URL = "https://api.apify.com/v2"


class ApifyConfigError(RuntimeError):
    """Apify is selected but not usable (missing token or actor IDs)."""


class ApifyError(RuntimeError):
    """An Apify actor run failed or returned nothing usable."""


def _first(item: dict, *keys: str) -> Any:
    for key in keys:
        if key in item and item[key] not in (None, ""):
            return item[key]
    return None


def _as_int(value: Any) -> int | None:
    if value in (None, ""):
        return None
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return None


class ApifyAdapter(DataSource):
    name = "apify"

    def __init__(
        self,
        settings: Settings | None = None,
        app_config: AppConfig | None = None,
        client: Any | None = None,
    ) -> None:
        settings = settings or get_settings()
        app_config = app_config or get_app_config()
        cfg = app_config.collection.get("apify", {}) or {}

        self.token = settings.apify_token
        if not self.token:
            raise ApifyConfigError(
                "APIFY_TOKEN is not set. Add it to your .env to use the apify adapter, "
                "or switch collection.adapter to 'mock' / 'import'."
            )
        self.base_url = (cfg.get("base_url") or _DEFAULT_BASE_URL).rstrip("/")
        self.profile_actor = cfg.get("profile_actor")
        self.posts_actor = cfg.get("posts_actor")
        if not self.profile_actor or not self.posts_actor:
            raise ApifyConfigError(
                "apify.profile_actor / apify.posts_actor missing from config/app.yaml"
            )
        self.posts_limit = int(cfg.get("posts_limit", 200))
        self._client = client  # injected in tests; lazily created otherwise

    # ------------------------------------------------------------------ #
    def _http(self) -> Any:
        if self._client is None:
            import httpx

            self._client = httpx.Client(timeout=120)
        return self._client

    def _run_actor(self, actor_id: str, run_input: dict) -> list[dict]:
        actor_path = actor_id.replace("/", "~")
        url = f"{self.base_url}/acts/{actor_path}/run-sync-get-dataset-items"
        response = self._http().post(url, params={"token": self.token}, json=run_input)
        status = getattr(response, "status_code", 0)
        if status >= 400:
            raise ApifyError(f"Apify actor {actor_id} returned HTTP {status}")
        data = response.json()
        if isinstance(data, dict):
            data = data.get("items", data.get("data", []))
        if not isinstance(data, list):
            raise ApifyError(f"Apify actor {actor_id} returned an unexpected payload")
        return data

    # ------------------------------------------------------------------ #
    def fetch_company_profile(self, linkedin_url: str) -> CompanyProfile:
        items = self._run_actor(
            self.profile_actor,
            {"companyUrl": linkedin_url, "identifier": linkedin_url},
        )
        if not items:
            raise ApifyError(f"No profile returned for {linkedin_url}")
        item = items[0]
        locations = _first(item, "locations", "geographies", "locationsRaw") or []
        if isinstance(locations, str):
            locations = [locations]
        specialties = _first(item, "specialties", "services", "specialities") or []
        if isinstance(specialties, str):
            specialties = [s.strip() for s in specialties.split(",") if s.strip()]
        return CompanyProfile(
            name=_first(item, "name", "title", "companyName"),
            linkedin_url=_first(item, "url", "linkedinUrl", "profileUrl") or linkedin_url,
            description=_first(item, "description", "about", "tagline"),
            industry=_first(item, "industry", "industries"),
            website=_first(item, "website", "websiteUrl"),
            followers=_as_int(_first(item, "followerCount", "followersCount", "followers")),
            geographies=[str(x) for x in locations],
            services=[str(x) for x in specialties],
            target_audience=_first(item, "targetAudience"),
            positioning=_first(item, "positioning", "tagline"),
        )

    # ------------------------------------------------------------------ #
    def fetch_posts(self, linkedin_url: str, since: datetime) -> list[RawPost]:
        items = self._run_actor(
            self.posts_actor,
            {"companyUrl": linkedin_url, "limit": self.posts_limit},
        )
        posts: list[RawPost] = []
        for item in items:
            posted_raw = _first(item, "postedAt", "date", "publishedAt", "time")
            if posted_raw is None:
                continue
            try:
                posted_at = (
                    posted_raw
                    if isinstance(posted_raw, datetime)
                    else datetime.fromisoformat(str(posted_raw).replace("Z", "+00:00"))
                )
            except ValueError:
                continue
            if posted_at.tzinfo is not None:
                posted_at = posted_at.replace(tzinfo=None)
            posts.append(
                RawPost(
                    url=_first(item, "url", "postUrl", "link") or "",
                    posted_at=posted_at,
                    content=_first(item, "text", "content", "postText") or "",
                    media_type=_first(item, "type", "mediaType", "postType") or "unknown",
                    reactions=_as_int(
                        _first(item, "numLikes", "likes", "reactions", "reactionsCount")
                    ),
                    comments=_as_int(_first(item, "numComments", "comments", "commentsCount")),
                    reposts=_as_int(_first(item, "numShares", "shares", "reposts", "repostsCount")),
                    hashtags=_first(item, "hashtags") or [],
                )
            )
        posts = [p for p in posts if p.url and p.posted_at >= since]
        posts.sort(key=lambda p: p.posted_at)
        return posts
