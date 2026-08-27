from datetime import datetime

from app.db.repos import CompetitorRepo, PostIntelligenceRepo, PostRepo, RunRepo
from app.schemas.collection import RawPost
from app.schemas.intelligence import KeywordTag, PostClassification

VERSIONS = {"format_classify": 1, "topic_classify": 1, "cta_extract": 1, "keyword_extract": 1}


def _seed(session, n=3):
    comp = CompetitorRepo(session).upsert(
        name="Acme", linkedin_url="https://www.linkedin.com/company/acme"
    )
    run = RunRepo(session).create(period_days=30, adapter="mock")
    posts = [
        RawPost(
            url=f"https://www.linkedin.com/feed/update/{i}",
            posted_at=datetime(2026, 1, 1, 12, 0),
            content=f"post {i} about cloud and automation",
            media_type="text",
        )
        for i in range(n)
    ]
    rows = PostRepo(session).insert_new(
        run_id=run.id, competitor_id=comp.id, posts=posts, source_adapter="mock"
    )
    session.commit()
    return run.id, rows


def _classification(idx: int) -> PostClassification:
    return PostClassification(
        index=idx,
        format="text_only",
        topic="cloud",
        sub_topic="migration",
        cta="none",
        keywords=[KeywordTag(term="cloud", category="industry_term")],
    )


def test_unclassified_returns_all_before_any_run(db_session):
    run_id, rows = _seed(db_session, 3)
    repo = PostIntelligenceRepo(db_session)
    assert [p.id for p in repo.unclassified(run_id, VERSIONS)] == [r.id for r in rows]


def test_upsert_then_unclassified_empty(db_session):
    run_id, rows = _seed(db_session, 3)
    repo = PostIntelligenceRepo(db_session)
    for i, row in enumerate(rows):
        repo.upsert(row.id, _classification(i), hashtags=["cloud"], prompt_versions=VERSIONS)
    db_session.commit()
    assert repo.unclassified(run_id, VERSIONS) == []
    assert repo.count_for_run(run_id) == 3
    stored = repo.get(rows[0].id)
    assert stored.format == "text_only"
    assert stored.hashtags == ["cloud"]
    assert stored.keywords[0]["term"] == "cloud"


def test_version_bump_invalidates_cache(db_session):
    run_id, rows = _seed(db_session, 2)
    repo = PostIntelligenceRepo(db_session)
    for i, row in enumerate(rows):
        repo.upsert(row.id, _classification(i), hashtags=[], prompt_versions=VERSIONS)
    db_session.commit()

    bumped = {**VERSIONS, "keyword_extract": 2}
    assert [p.id for p in repo.unclassified(run_id, bumped)] == [r.id for r in rows]


def test_upsert_is_idempotent_on_post_id(db_session):
    _run_id, rows = _seed(db_session, 1)
    repo = PostIntelligenceRepo(db_session)
    repo.upsert(rows[0].id, _classification(0), hashtags=[], prompt_versions=VERSIONS)
    repo.upsert(rows[0].id, _classification(0), hashtags=[], prompt_versions=VERSIONS)
    db_session.commit()
    assert repo.count_for_run(_run_id) == 1
