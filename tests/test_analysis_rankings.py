"""AnalysisRepo ranking queries against a hand-computed fixture (no LLM)."""

from datetime import datetime

import pytest

from app.analysis.engagement import score_run
from app.db.repos import (
    AnalysisRepo,
    CompetitorRepo,
    PostIntelligenceRepo,
    PostRepo,
    ProfileRepo,
    RunRepo,
)
from app.schemas.collection import CompanyProfile, RawPost
from app.schemas.intelligence import KeywordTag, PostClassification

# (key, format, topic, cta, reactions) — comments/reposts are 0 so score == reactions
_A = [
    ("a0", "carousel", "cloud", "download", 100),
    ("a1", "video", "cloud", "none", 50),
    ("a2", "carousel", "ai", "none", 10),
]
_B = [
    ("b0", "text_only", "ai", "none", 200),
    ("b1", "video", "cloud", "download", 20),
]


def _add(session, *, run_id, competitor_id, rows):
    out = {}
    for i, (key, fmt, topic, cta, reactions) in enumerate(rows):
        created = PostRepo(session).insert_new(
            run_id=run_id,
            competitor_id=competitor_id,
            source_adapter="mock",
            posts=[
                RawPost(
                    url=f"https://example.test/{key}",
                    posted_at=datetime(2026, 1, 1 + i, 9, 0),
                    content=f"{key} about {topic}",
                    media_type="text",
                    reactions=reactions,
                    comments=0,
                    reposts=0,
                )
            ],
        )
        PostIntelligenceRepo(session).upsert(
            created[0].id,
            PostClassification(
                index=i,
                format=fmt,
                topic=topic,
                sub_topic=None,
                cta=cta,
                keywords=[KeywordTag(term=topic, category="industry_term")],
            ),
            hashtags=[],
            prompt_versions={"format_classify": 1},
        )
        out[key] = created[0].id
    return out


@pytest.fixture
def scored_run(db_session):
    a = CompetitorRepo(db_session).upsert(
        name="Acme", linkedin_url="https://www.linkedin.com/company/acme"
    )
    b = CompetitorRepo(db_session).upsert(
        name="Beta", linkedin_url="https://www.linkedin.com/company/beta"
    )
    ProfileRepo(db_session).upsert(a.id, CompanyProfile(followers=10_000))
    ProfileRepo(db_session).upsert(b.id, CompanyProfile(followers=1_000))
    run = RunRepo(db_session).create(period_days=30, adapter="mock")
    ids = _add(db_session, run_id=run.id, competitor_id=a.id, rows=_A)
    ids |= _add(db_session, run_id=run.id, competitor_id=b.id, rows=_B)
    db_session.commit()
    score_run(db_session, run_id=run.id)
    db_session.commit()
    return run.id, a.id, b.id, ids


def test_top_posts_5_and_10_are_score_ordered(db_session, scored_run):
    run_id, *_ = scored_run
    repo = AnalysisRepo(db_session)
    top5 = repo.top_posts(run_id, 5)
    assert [p.url.rsplit("/", 1)[-1] for p in top5] == ["b0", "a0", "a1", "b1", "a2"]
    assert [p.engagement_score for p in top5] == [200, 100, 50, 20, 10]
    assert repo.top_posts(run_id, 10) == top5  # only 5 posts exist
    assert [p.url.rsplit("/", 1)[-1] for p in repo.top_posts(run_id, 2)] == ["b0", "a0"]


def test_top_post_rate_is_follower_normalised(db_session, scored_run):
    run_id, *_ = scored_run
    by_key = {p.url.rsplit("/", 1)[-1]: p for p in AnalysisRepo(db_session).top_posts(run_id, 10)}
    assert by_key["a0"].engagement_rate == pytest.approx(1.0)  # 100 / 10000
    assert by_key["b0"].engagement_rate == pytest.approx(20.0)  # 200 / 1000


def test_top_posts_by_competitor(db_session, scored_run):
    run_id, a_id, b_id, _ = scored_run
    groups = {
        g.competitor_id: g for g in AnalysisRepo(db_session).top_posts_by_competitor(run_id, 2)
    }
    assert [p.url.rsplit("/", 1)[-1] for p in groups[a_id].posts] == ["a0", "a1"]
    assert [p.url.rsplit("/", 1)[-1] for p in groups[b_id].posts] == ["b0", "b1"]


def test_top_formats(db_session, scored_run):
    run_id, *_ = scored_run
    rows = {r.format: r for r in AnalysisRepo(db_session).top_formats(run_id)}
    assert [r.format for r in AnalysisRepo(db_session).top_formats(run_id)] == [
        "text_only",
        "carousel",
        "video",
    ]
    assert rows["carousel"].posts == 2
    assert rows["carousel"].avg_engagement == pytest.approx(55.0)
    assert rows["carousel"].best_post == "https://example.test/a0"
    assert rows["carousel"].best_post_score == 100
    assert rows["carousel"].avg_rate == pytest.approx((1.0 + 0.1) / 2)


def test_top_topics(db_session, scored_run):
    run_id, *_ = scored_run
    rows = {r.topic: r for r in AnalysisRepo(db_session).top_topics(run_id)}
    assert [r.topic for r in AnalysisRepo(db_session).top_topics(run_id)] == ["ai", "cloud"]
    assert rows["cloud"].posts == 3
    assert rows["cloud"].avg_engagement == pytest.approx(170 / 3)
    assert rows["ai"].best_post == "https://example.test/b0"


def test_top_ctas(db_session, scored_run):
    run_id, *_ = scored_run
    rows = {r.cta: r for r in AnalysisRepo(db_session).top_ctas(run_id)}
    assert [r.cta for r in AnalysisRepo(db_session).top_ctas(run_id)] == ["none", "download"]
    assert rows["none"].posts == 3
    assert rows["none"].avg_engagement == pytest.approx(260 / 3)
    assert rows["download"].avg_engagement == pytest.approx(60.0)
