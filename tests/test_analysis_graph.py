"""End-to-end coverage for the EPIC-04 analysis stage: score -> rank -> detect_campaigns."""

from datetime import datetime

import pytest

from app.analysis.graph import analyze_run
from app.core.model_router import ModelRouter
from app.datasources.collector import collect_for_run
from app.datasources.mock import MockAdapter
from app.db.repos import CampaignRepo, CompetitorRepo, PostIntelligenceRepo, PostRepo, RunRepo
from app.intelligence.fakes import register_classification_fakes
from app.intelligence.graph import classify_posts_for_run

NOW = datetime(2026, 3, 15, 12, 0)


@pytest.fixture
def analysis_router(settings, models_config, fake_llm):
    register_classification_fakes(fake_llm)
    return ModelRouter(settings, models_config, fake_llm=fake_llm, backoff_base=0)


def _collected_classified_run(session, router, registry):
    repo = CompetitorRepo(session)
    competitors = [
        repo.upsert(name="Acme", linkedin_url="https://www.linkedin.com/company/acme"),
        repo.upsert(name="Beta", linkedin_url="https://www.linkedin.com/company/beta-corp"),
    ]
    run = RunRepo(session).create(period_days=30, adapter="mock")
    collect_for_run(
        session,
        run_id=run.id,
        competitors=competitors,
        adapter=MockAdapter(now=NOW),
        period_days=30,
        now=NOW,
    )
    session.commit()
    classify_posts_for_run(session, run_id=run.id, router=router, registry=registry)
    session.commit()
    return run.id


def test_analyze_run_scores_ranks_and_detects(db_session, analysis_router, prompt_registry):
    run_id = _collected_classified_run(db_session, analysis_router, prompt_registry)

    result = analyze_run(
        db_session, run_id=run_id, router=analysis_router, registry=prompt_registry
    )

    total_posts = PostRepo(db_session).count_for_run(run_id)
    classified = PostIntelligenceRepo(db_session).count_for_run(run_id)
    assert total_posts > 0
    assert result.score.posts_scored == classified == total_posts

    # every classified post carries a score
    for row in PostIntelligenceRepo(db_session).list_for_run(run_id):
        assert row.engagement_score is not None
        assert row.engagement_rate is not None  # mock adapter always has followers

    # rankings are score-ordered and bounded
    scores = [p.engagement_score for p in result.rankings.top_posts]
    assert scores == sorted(scores, reverse=True)
    assert len(result.rankings.top_posts) <= 20
    assert result.rankings.top_formats  # at least one format bucket

    # campaigns persisted match the stage result
    assert result.campaigns.persisted == CampaignRepo(db_session).count_for_run(run_id)
    assert result.campaigns.persisted >= 1
    assert RunRepo(db_session).get(run_id).stage == "campaigns"


def test_analyze_run_handles_competitor_without_followers(
    db_session, analysis_router, prompt_registry
):
    from app.db.repos import ProfileRepo
    from app.schemas.collection import CompanyProfile, RawPost
    from app.schemas.intelligence import KeywordTag, PostClassification

    comp = CompetitorRepo(db_session).upsert(
        name="NoFollowers", linkedin_url="https://www.linkedin.com/company/nf"
    )
    ProfileRepo(db_session).upsert(comp.id, CompanyProfile(followers=None))
    run = RunRepo(db_session).create(period_days=30, adapter="mock")
    created = PostRepo(db_session).insert_new(
        run_id=run.id,
        competitor_id=comp.id,
        source_adapter="mock",
        posts=[
            RawPost(
                url=f"https://example.test/nf-{i}",
                posted_at=datetime(2026, 3, 1 + i, 9, 0),
                content=f"post {i} about ai",
                media_type="text",
                reactions=10 * (i + 1),
                comments=1,
                reposts=0,
            )
            for i in range(3)
        ],
    )
    for i, row in enumerate(created):
        PostIntelligenceRepo(db_session).upsert(
            row.id,
            PostClassification(
                index=i,
                format="thought_leadership",
                topic="ai",
                sub_topic="ai stuff",
                cta="none",
                keywords=[KeywordTag(term="ai", category="industry_term")],
            ),
            hashtags=[],
            prompt_versions={"format_classify": 1},
        )
    db_session.commit()

    result = analyze_run(
        db_session, run_id=run.id, router=analysis_router, registry=prompt_registry
    )

    assert result.score.posts_scored == 3
    assert result.score.with_rate == 0
    for row in PostIntelligenceRepo(db_session).list_for_run(run.id):
        assert row.engagement_score is not None
        assert row.engagement_rate is None
    for fmt in result.rankings.top_formats:
        assert fmt.avg_rate is None
