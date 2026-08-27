"""Top content report: ranking strategy + batched WhyItWorked parse (EPIC-05)."""

from datetime import datetime

import pytest

from app.analysis.engagement import score_run
from app.analysis.mapping_fakes import register_mapping_fakes
from app.analysis.top_content import _Candidate, build_top_content, rank_candidates
from app.core.model_router import ModelRouter
from app.db.repos import CompetitorRepo, PostIntelligenceRepo, PostRepo, ProfileRepo, RunRepo
from app.schemas.collection import CompanyProfile, RawPost
from app.schemas.intelligence import KeywordTag, PostClassification


@pytest.fixture
def mapping_router(settings, models_config, fake_llm):
    register_mapping_fakes(fake_llm)
    return ModelRouter(settings, models_config, fake_llm=fake_llm, backoff_base=0)


def _seed(db_session, *, n, followers):
    comp = CompetitorRepo(db_session).upsert(
        name="Acme", linkedin_url="https://www.linkedin.com/company/acme"
    )
    ProfileRepo(db_session).upsert(comp.id, CompanyProfile(followers=followers))
    run = RunRepo(db_session).create(period_days=30, adapter="mock")
    for i in range(n):
        created = PostRepo(db_session).insert_new(
            run_id=run.id,
            competitor_id=comp.id,
            source_adapter="mock",
            posts=[
                RawPost(
                    url=f"https://example.test/p{i}",
                    posted_at=datetime(2026, 1, 1, 9) if i else datetime(2026, 1, 2, 9),
                    content=f"Acme | 2026-01-0{(i % 8) + 1} | thoughts on ai and data {i}",
                    media_type="text",
                    reactions=(i + 1) * 10,
                    comments=0,
                    reposts=0,
                )
            ],
        )
        PostIntelligenceRepo(db_session).upsert(
            created[0].id,
            PostClassification(
                index=i,
                format="thought_leadership",
                topic="ai",
                sub_topic=None,
                cta="none",
                keywords=[KeywordTag(term="ai", category="industry_term")],
            ),
            hashtags=[],
            prompt_versions={"format_classify": 1},
        )
    db_session.commit()
    score_run(db_session, run_id=run.id)
    db_session.commit()
    return run.id


def test_rank_strategy_prefers_rate_when_all_present():
    cands = [
        _Candidate(1, "A", "u1", datetime(2026, 1, 1), "text_only", "ai", 900.0, 1.0),
        _Candidate(2, "B", "u2", datetime(2026, 1, 1), "text_only", "ai", 100.0, 9.0),
    ]
    top, ranked_by = rank_candidates(cands, 10)
    assert ranked_by == "engagement_rate"
    assert [c.post_id for c in top] == [2, 1]  # rate order, not score order


def test_rank_strategy_falls_back_to_score_when_rate_missing():
    cands = [
        _Candidate(1, "A", "u1", datetime(2026, 1, 1), "text_only", "ai", 900.0, None),
        _Candidate(2, "B", "u2", datetime(2026, 1, 1), "text_only", "ai", 100.0, 9.0),
    ]
    top, ranked_by = rank_candidates(cands, 10)
    assert ranked_by == "engagement_score"
    assert [c.post_id for c in top] == [1, 2]


def test_report_has_20_rows_each_with_why(db_session, mapping_router):
    run_id = _seed(db_session, n=25, followers=10_000)
    result = build_top_content(
        db_session, run_id=run_id, router=mapping_router, registry=_registry()
    )
    report = result.report
    assert report.ranked_by == "engagement_rate"
    assert len(report.items) == 20
    assert [it.rank for it in report.items] == list(range(1, 21))
    for it in report.items:
        assert it.why.summary and it.why.hook and it.why.length_note
    # score-ordered (rate is monotonic in score here since one competitor)
    scores = [it.engagement_score for it in report.items]
    assert scores == sorted(scores, reverse=True)
    assert RunRepo(db_session).get(run_id).stage == "top_content"


def test_report_returns_all_when_fewer_than_n(db_session, mapping_router):
    run_id = _seed(db_session, n=6, followers=None)
    result = build_top_content(
        db_session, run_id=run_id, router=mapping_router, registry=_registry()
    )
    assert result.report.ranked_by == "engagement_score"
    assert len(result.report.items) == 6


def _registry():
    from app.config.settings import PROMPTS_DIR
    from app.core.prompt_registry import PromptRegistry

    return PromptRegistry(PROMPTS_DIR)
