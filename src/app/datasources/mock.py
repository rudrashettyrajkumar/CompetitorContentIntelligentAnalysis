"""Deterministic synthetic data source — powers ``make demo`` and every test.

Everything is seeded from the company slug, so the same competitor always yields the
same profile and the same post history. Distributions are deliberately realistic:
a business-page format mix, engagement correlated with format, follower counts in a
plausible 10k–500k band, and topic-flavoured post text.
"""

from __future__ import annotations

import hashlib
from datetime import datetime, timedelta
from random import Random

from app.datasources.base import DataSource
from app.schemas.collection import CompanyProfile, RawPost

# --- knobs (kept here rather than config: this adapter is test/demo scaffolding) ---
_POSTS_PER_90_DAYS = (30, 60)
_HORIZON_DAYS = 90
_FOLLOWER_BAND = (10_000, 500_000)

_FORMAT_WEIGHTS: dict[str, float] = {
    "text": 0.28,
    "image": 0.24,
    "carousel": 0.14,
    "video": 0.12,
    "article": 0.10,
    "document": 0.08,
    "poll": 0.04,
}
# Relative reach multiplier per format (carousels/video over-index, text under-indexes).
_FORMAT_ENGAGEMENT: dict[str, float] = {
    "carousel": 1.6,
    "video": 1.5,
    "document": 1.3,
    "image": 1.0,
    "poll": 0.9,
    "article": 0.8,
    "text": 0.7,
}

_TOPICS: list[tuple[str, list[str]]] = [
    ("AI & automation", ["AI", "Automation", "FutureOfWork"]),
    ("customer success", ["CustomerSuccess", "CX", "Retention"]),
    ("product launch", ["ProductLaunch", "Release", "Innovation"]),
    ("industry trends", ["IndustryTrends", "MarketInsights", "Research"]),
    ("company culture", ["Culture", "LifeAt", "Values"]),
    ("hiring & team", ["Hiring", "WeAreHiring", "Careers"]),
    ("thought leadership", ["ThoughtLeadership", "Leadership", "Strategy"]),
    ("case study", ["CaseStudy", "CustomerStory", "ROI"]),
    ("events & webinars", ["Webinar", "Event", "Community"]),
    ("sustainability", ["Sustainability", "ESG", "Impact"]),
]

_GEOS = [
    "North America",
    "United States",
    "Canada",
    "United Kingdom",
    "DACH",
    "Nordics",
    "APAC",
    "Singapore",
    "Australia",
    "Middle East",
]
_SERVICES = [
    "platform licensing",
    "professional services",
    "managed operations",
    "advisory & consulting",
    "training & enablement",
    "support & success plans",
    "integrations & APIs",
]
_AUDIENCES = [
    "mid-market operations leaders",
    "enterprise IT decision makers",
    "revenue and growth teams",
    "founders and heads of product",
    "security and compliance leaders",
]

_OPENERS = {
    "text": "A quick thought on",
    "image": "Behind the scenes:",
    "carousel": "Swipe through our breakdown of",
    "video": "Watch: our team on",
    "article": "New on our blog —",
    "document": "Download our latest guide to",
    "poll": "We want your take on",
}


def _slug_of(linkedin_url: str) -> str:
    tail = linkedin_url.rstrip("/").rsplit("/company/", 1)[-1]
    return tail.rsplit("/", 1)[-1].lower() or "company"


def _seed(linkedin_url: str, stream: str) -> int:
    digest = hashlib.sha256(f"{_slug_of(linkedin_url)}:{stream}".encode()).digest()
    return int.from_bytes(digest[:8], "big")


def _weighted_choice(rng: Random, weights: dict[str, float]) -> str:
    keys = list(weights)
    return rng.choices(keys, weights=[weights[k] for k in keys], k=1)[0]


def _title_from_slug(slug: str) -> str:
    return " ".join(part.capitalize() for part in slug.replace("_", "-").split("-"))


def _follower_count(linkedin_url: str) -> int:
    """Stable follower count for a company, shared by profile + post generation."""
    return Random(_seed(linkedin_url, "followers")).randint(*_FOLLOWER_BAND)


class MockAdapter(DataSource):
    name = "mock"

    def __init__(self, now: datetime | None = None) -> None:
        self._now = now or datetime.utcnow()

    # ------------------------------------------------------------------ #
    def fetch_company_profile(self, linkedin_url: str) -> CompanyProfile:
        rng = Random(_seed(linkedin_url, "profile"))
        slug = _slug_of(linkedin_url)
        name = _title_from_slug(slug)
        followers = _follower_count(linkedin_url)
        geographies = rng.sample(_GEOS, k=rng.randint(2, 4))
        services = rng.sample(_SERVICES, k=rng.randint(2, 4))
        audience = rng.choice(_AUDIENCES)
        primary_topic = rng.choice(_TOPICS)[0]
        return CompanyProfile(
            name=name,
            linkedin_url=f"https://www.linkedin.com/company/{slug}",
            description=(
                f"{name} helps {audience} move faster with {services[0]} and "
                f"{services[1] if len(services) > 1 else 'expert support'}. "
                f"Trusted across {', '.join(geographies)}."
            ),
            industry=None,
            website=f"https://www.{slug.replace('_', '-')}.example",
            followers=followers,
            geographies=geographies,
            services=services,
            target_audience=audience,
            positioning=(f"Positioned as a {primary_topic}-led alternative for {audience}."),
        )

    # ------------------------------------------------------------------ #
    def fetch_posts(self, linkedin_url: str, since: datetime) -> list[RawPost]:
        rng = Random(_seed(linkedin_url, "posts"))
        slug = _slug_of(linkedin_url)
        followers = _follower_count(linkedin_url)

        count = rng.randint(*_POSTS_PER_90_DAYS)
        posts: list[RawPost] = []
        for i in range(count):
            age_days = rng.uniform(0, _HORIZON_DAYS)
            posted_at = self._now - timedelta(days=age_days, hours=rng.uniform(0, 24))
            media_type = _weighted_choice(rng, _FORMAT_WEIGHTS)
            topic, tag_pool = rng.choice(_TOPICS)
            hashtags = [t.lower() for t in rng.sample(tag_pool, k=min(2, len(tag_pool)))]

            base_rate = rng.uniform(0.004, 0.02) * _FORMAT_ENGAGEMENT[media_type]
            reactions = max(1, int(followers * base_rate * rng.uniform(0.6, 1.4)))
            comments = max(0, int(reactions * rng.uniform(0.02, 0.09)))
            reposts = max(0, int(reactions * rng.uniform(0.01, 0.06)))

            opener = _OPENERS[media_type]
            content = (
                f"{opener} {topic}. "
                f"Here is what {_title_from_slug(slug)} is seeing this quarter and "
                f"why it matters for teams betting on {topic}. "
                + " ".join(f"#{t}" for t in tag_pool[:2])
            )
            posts.append(
                RawPost(
                    url=f"https://www.linkedin.com/feed/update/urn:li:activity:{slug}-{i:03d}",
                    posted_at=posted_at,
                    content=content,
                    media_type=media_type,
                    reactions=reactions,
                    comments=comments,
                    reposts=reposts,
                    hashtags=hashtags,
                )
            )

        posts.sort(key=lambda p: p.posted_at)
        return [p for p in posts if p.posted_at >= since]
