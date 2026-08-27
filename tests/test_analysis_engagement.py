"""Engagement scoring: weighted score, follower-normalised rate, missing-metric flag."""

from datetime import datetime

import pytest

from app.analysis.engagement import (
    engagement_rate,
    load_weights,
    score_post,
    score_run,
)
from app.config.settings import AppConfig
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

WEIGHTS = {"reactions": 1.0, "comments": 2.0, "reposts": 3.0}


def test_score_is_weighted_sum():
    score, complete = score_post(reactions=10, comments=2, reposts=1, weights=WEIGHTS)
    assert score == 10 * 1 + 2 * 2 + 1 * 3
    assert complete is True


def test_missing_metric_counts_as_zero_but_flags_incomplete():
    score, complete = score_post(reactions=10, comments=None, reposts=1, weights=WEIGHTS)
    assert score == 10 * 1 + 0 + 1 * 3
    assert complete is False


def test_rate_is_none_without_followers():
    assert engagement_rate(500.0, None) is None
    assert engagement_rate(500.0, 0) is None


def test_rate_is_percentage_of_followers():
    assert engagement_rate(500.0, 10_000) == pytest.approx(5.0)


def test_weights_come_from_config():
    cfg = AppConfig(engagement={"weights": {"reactions": 2, "comments": 5, "reposts": 9}})
    assert load_weights(cfg) == {"reactions": 2.0, "comments": 5.0, "reposts": 9.0}


def test_weights_fall_back_to_defaults_when_unset():
    assert load_weights(AppConfig()) == {"reactions": 1.0, "comments": 2.0, "reposts": 3.0}


# --------------------------------------------------------------------------- #
def _seed_post(session, *, run_id, competitor_id, idx, reactions, comments, reposts):
    rows = PostRepo(session).insert_new(
        run_id=run_id,
        competitor_id=competitor_id,
        source_adapter="mock",
        posts=[
            RawPost(
                url=f"https://www.linkedin.com/feed/update/{competitor_id}-{idx}",
                posted_at=datetime(2026, 1, 1, 9, 0),
                content=f"post {idx} about cloud",
                media_type="text",
                reactions=reactions,
                comments=comments,
                reposts=reposts,
            )
        ],
    )
    PostIntelligenceRepo(session).upsert(
        rows[0].id,
        PostClassification(
            index=idx,
            format="text_only",
            topic="cloud",
            sub_topic="migration",
            cta="none",
            keywords=[KeywordTag(term="cloud", category="industry_term")],
        ),
        hashtags=[],
        prompt_versions={"format_classify": 1},
    )
    return rows[0].id


def test_score_run_persists_scores_and_rates(db_session):
    comp = CompetitorRepo(db_session).upsert(
        name="Acme", linkedin_url="https://www.linkedin.com/company/acme"
    )
    ProfileRepo(db_session).upsert(comp.id, CompanyProfile(followers=10_000))
    run = RunRepo(db_session).create(period_days=30, adapter="mock")
    pid = _seed_post(
        db_session,
        run_id=run.id,
        competitor_id=comp.id,
        idx=0,
        reactions=100,
        comments=10,
        reposts=5,
    )
    db_session.commit()

    result = score_run(db_session, run_id=run.id)
    db_session.commit()

    assert result.posts_scored == 1
    assert result.with_rate == 1
    assert result.incomplete_metrics == 0
    row = PostIntelligenceRepo(db_session).get(pid)
    assert row.engagement_score == 100 * 1 + 10 * 2 + 5 * 3  # 135
    assert row.engagement_rate == pytest.approx(135 / 10_000 * 100)
    assert row.metrics_complete is True


def test_score_run_without_followers_yields_null_rate_and_no_crash(db_session):
    comp = CompetitorRepo(db_session).upsert(
        name="NoFollowers", linkedin_url="https://www.linkedin.com/company/nf"
    )
    # profile row exists but followers is unknown
    ProfileRepo(db_session).upsert(comp.id, CompanyProfile(followers=None))
    run = RunRepo(db_session).create(period_days=30, adapter="mock")
    pid = _seed_post(
        db_session,
        run_id=run.id,
        competitor_id=comp.id,
        idx=0,
        reactions=50,
        comments=None,
        reposts=2,
    )
    db_session.commit()

    result = score_run(db_session, run_id=run.id)
    db_session.commit()

    assert result.posts_scored == 1
    assert result.with_rate == 0
    assert result.incomplete_metrics == 1
    row = PostIntelligenceRepo(db_session).get(pid)
    assert row.engagement_score == 50 * 1 + 0 + 2 * 3
    assert row.engagement_rate is None
    assert row.metrics_complete is False


def test_metrics_for_run_left_joins_missing_profile(db_session):
    comp = CompetitorRepo(db_session).upsert(
        name="NoProfile", linkedin_url="https://www.linkedin.com/company/np"
    )
    run = RunRepo(db_session).create(period_days=30, adapter="mock")
    _seed_post(
        db_session, run_id=run.id, competitor_id=comp.id, idx=0, reactions=1, comments=1, reposts=1
    )
    db_session.commit()

    rows = AnalysisRepo(db_session).metrics_for_run(run.id)
    assert len(rows) == 1
    assert rows[0].followers is None
