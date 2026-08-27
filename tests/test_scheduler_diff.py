"""Period diff on two seeded runs with known planted changes (EPIC-08)."""

from datetime import datetime

import pytest

from app.analysis.engagement import score_run
from app.db.repos import (
    CampaignRepo,
    CompetitorRepo,
    PostIntelligenceRepo,
    PostRepo,
    ProfileRepo,
    RunRepo,
    StrategyProfileRepo,
)
from app.scheduler.diff import compute_period_diff
from app.schemas.analysis import ValidatedCampaign
from app.schemas.collection import CompanyProfile, RawPost
from app.schemas.intelligence import KeywordTag, PostClassification
from app.schemas.strategy_map import StrategyProfile


# (topic, format, score, keyword) rows, repeated per spec
def _seed_run(session, *, tag, rows, campaigns, profile):
    comp = CompetitorRepo(session).upsert(
        name="Acme", linkedin_url="https://www.linkedin.com/company/acme"
    )
    ProfileRepo(session).upsert(comp.id, CompanyProfile(followers=10_000))
    run = RunRepo(session).create(period_days=30, adapter="mock")
    ids = []
    for i, (topic, fmt, score, kw) in enumerate(rows):
        created = PostRepo(session).insert_new(
            run_id=run.id,
            competitor_id=comp.id,
            source_adapter="mock",
            posts=[
                RawPost(
                    url=f"https://example.test/{tag}-{i}",
                    posted_at=datetime(2026, 1, 1 + (i % 27), 9),
                    content=f"{tag} post {i}",
                    media_type="text",
                    reactions=score,
                    comments=0,
                    reposts=0,
                )
            ],
        )
        pid = created[0].id
        ids.append(pid)
        PostIntelligenceRepo(session).upsert(
            pid,
            PostClassification(
                index=i,
                format=fmt,
                topic=topic,
                sub_topic=None,
                cta="none",
                keywords=[KeywordTag(term=kw, category="frequent")],
            ),
            hashtags=[],
            prompt_versions={"format_classify": 1},
        )
    session.commit()
    score_run(session, run_id=run.id)
    session.commit()

    validated = [
        ValidatedCampaign(
            competitor_id=comp.id,
            name=name,
            theme=name,
            post_ids=[ids[j] for j in idxs],
            post_urls=[f"https://example.test/{tag}-{j}" for j in idxs],
            start_date=datetime(2026, 1, 1, 9),
            end_date=datetime(2026, 1, 10, 9),
        )
        for name, idxs in campaigns.items()
    ]
    CampaignRepo(session).replace_for_run(run.id, validated)

    StrategyProfileRepo(session).replace_for_run(
        run.id,
        [
            StrategyProfile(
                competitor="Acme",
                competitor_id=comp.id,
                primary_themes=["ai"],
                content_mix=profile["mix"],
                best_format=profile["best_format"],
                best_topic="ai",
                posting_frequency_per_week=profile["cadence"],
                engagement_windows=["Tue"],
                positioning_summary="x",
            )
        ],
    )
    session.commit()
    return run.id


_BASELINE = (
    [("ai", "text_only", 100, "legacy") for _ in range(4)]
    + [("ai", "text_only", 100, "agentic") for _ in range(2)]
    + [("cloud", "carousel", 100, "stable") for _ in range(4)]
)
_CURRENT = (
    [("ai", "text_only", 300, "agentic") for _ in range(6)]
    + [("cloud", "carousel", 110, "stable") for _ in range(4)]
    + [("ai", "text_only", 300, "legacy")]
)


@pytest.fixture
def two_runs(db_session):
    base = _seed_run(
        db_session,
        tag="b",
        rows=_BASELINE,
        campaigns={"Cloud push": [6, 7, 8]},
        profile={"cadence": 2.0, "best_format": "text_only", "mix": {"text": 60.0, "visual": 40.0}},
    )
    cur = _seed_run(
        db_session,
        tag="c",
        rows=_CURRENT,
        campaigns={"Cloud push": [6, 7, 8], "AI blitz": [0, 1, 2]},
        profile={"cadence": 5.0, "best_format": "carousel", "mix": {"visual": 60.0, "text": 40.0}},
    )
    return base, cur


def test_diff_detects_and_ignores_noise(db_session, two_runs):
    base, cur = two_runs
    diff = compute_period_diff(db_session, baseline_run_id=base, current_run_id=cur)

    assert diff.new_campaigns == ["AI blitz"]
    assert diff.ended_campaigns == []

    emerging = {d.term for d in diff.emerging_keywords}
    fading = {d.term for d in diff.fading_keywords}
    assert "agentic" in emerging  # 2 -> 6, growth 3x
    assert "legacy" in fading  # 4 -> 1
    assert "stable" not in emerging and "stable" not in fading  # 4 -> 4, below threshold

    shifted = {s.topic for s in diff.topic_performance_shifts}
    assert "ai" in shifted  # 100 -> 300
    assert "cloud" not in shifted  # 100 -> 110, +10% < 25%

    assert any(c.field == "cadence" for c in diff.profile_changes)
    assert any(c.field == "best_format" for c in diff.profile_changes)

    assert diff.strategy_refresh_recommended is True
    assert diff.refresh_reasons


def test_thresholds_are_configurable(db_session, two_runs):
    base, cur = two_runs
    strict = {
        "topic_shift_pct": 5.0,
        "emerging_keyword_growth": 10.0,
        "refresh_shift_threshold": 99,
    }
    diff = compute_period_diff(
        db_session,
        baseline_run_id=base,
        current_run_id=cur,
        app_config=type("C", (), {"loop": strict})(),
    )
    assert diff.topic_performance_shifts == []
    assert diff.emerging_keywords == []
    assert diff.strategy_refresh_recommended is False


def test_quiet_diff_recommends_no_refresh(db_session):
    a = _seed_run(
        db_session,
        tag="q1",
        rows=_BASELINE,
        campaigns={"Cloud push": [6, 7, 8]},
        profile={"cadence": 2.0, "best_format": "text_only", "mix": {"text": 60.0}},
    )
    b = _seed_run(
        db_session,
        tag="q2",
        rows=_BASELINE,
        campaigns={"Cloud push": [6, 7, 8]},
        profile={"cadence": 2.0, "best_format": "text_only", "mix": {"text": 60.0}},
    )
    diff = compute_period_diff(db_session, baseline_run_id=a, current_run_id=b)
    assert diff.material_change_count() == 0
    assert diff.strategy_refresh_recommended is False
