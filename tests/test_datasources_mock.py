from collections import Counter
from datetime import datetime, timedelta

import pytest

from app.datasources.mock import MockAdapter

URL_A = "https://www.linkedin.com/company/nimbus-analytics"
URL_B = "https://www.linkedin.com/company/pangolin-security"
NOW = datetime(2026, 8, 27)


@pytest.fixture
def adapter():
    return MockAdapter(now=NOW)


def test_profile_is_deterministic(adapter):
    p1 = adapter.fetch_company_profile(URL_A)
    p2 = MockAdapter(now=datetime(2020, 1, 1)).fetch_company_profile(URL_A)
    assert p1.model_dump() == p2.model_dump()
    assert 10_000 <= p1.followers <= 500_000
    assert p1.geographies and p1.services


def test_profile_differs_per_company(adapter):
    assert (
        adapter.fetch_company_profile(URL_A).followers
        != adapter.fetch_company_profile(URL_B).followers
    )


def test_posts_deterministic(adapter):
    since = NOW - timedelta(days=90)
    a = adapter.fetch_posts(URL_A, since)
    b = MockAdapter(now=NOW).fetch_posts(URL_A, since)
    assert [p.url for p in a] == [p.url for p in b]
    assert [p.reactions for p in a] == [p.reactions for p in b]


def test_posts_count_and_ordering(adapter):
    posts = adapter.fetch_posts(URL_A, NOW - timedelta(days=90))
    assert 30 <= len(posts) <= 60
    assert posts == sorted(posts, key=lambda p: p.posted_at)
    assert all(NOW - timedelta(days=91) <= p.posted_at <= NOW for p in posts)


def test_period_filtering_is_a_strict_window(adapter):
    full = adapter.fetch_posts(URL_A, NOW - timedelta(days=90))
    week = adapter.fetch_posts(URL_A, NOW - timedelta(days=7))
    assert len(week) < len(full)
    assert all(p.posted_at >= NOW - timedelta(days=7) for p in week)
    # 7-day slice is a subset of the 90-day pull
    assert {p.url for p in week} <= {p.url for p in full}


def test_distributions_are_sane(adapter):
    posts = adapter.fetch_posts(URL_A, NOW - timedelta(days=90))
    formats = Counter(p.media_type for p in posts)
    assert len(formats) >= 3  # a real mix, not one format
    assert all(p.reactions >= 1 for p in posts)
    assert all(p.comments <= p.reactions for p in posts)
    assert all(p.hashtags for p in posts)
