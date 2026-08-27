from datetime import datetime, timedelta

from app.datasources.base import DataSource
from app.datasources.collector import collect_for_run
from app.datasources.mock import MockAdapter
from app.db.repos import CompetitorRepo, PostRepo, ProfileRepo, RunRepo
from app.schemas.collection import CompanyProfile, RawPost

NOW = datetime(2026, 8, 27)


def _competitors(session):
    repo = CompetitorRepo(session)
    return [
        repo.upsert(
            name="Nimbus", linkedin_url="https://www.linkedin.com/company/nimbus-analytics"
        ),
        repo.upsert(
            name="Pangolin", linkedin_url="https://www.linkedin.com/company/pangolin-security"
        ),
    ]


def test_collect_persists_profiles_and_posts(db_session):
    competitors = _competitors(db_session)
    run = RunRepo(db_session).create(period_days=90, adapter="mock")
    result = collect_for_run(
        db_session,
        run_id=run.id,
        competitors=competitors,
        adapter=MockAdapter(now=NOW),
        period_days=90,
        now=NOW,
    )
    assert result.profiles_collected == 2
    assert result.posts_inserted > 0
    assert PostRepo(db_session).count_for_run(run.id) == result.posts_inserted
    assert ProfileRepo(db_session).get(competitors[0].id).followers is not None
    assert RunRepo(db_session).get(run.id).stage == "collect"


def test_rerun_does_not_duplicate_posts(db_session):
    competitors = _competitors(db_session)
    adapter = MockAdapter(now=NOW)

    run1 = RunRepo(db_session).create(period_days=90, adapter="mock")
    r1 = collect_for_run(
        db_session,
        run_id=run1.id,
        competitors=competitors,
        adapter=adapter,
        period_days=90,
        now=NOW,
    )
    total_after_first = PostRepo(db_session).count_all()
    assert total_after_first == r1.posts_inserted

    run2 = RunRepo(db_session).create(period_days=90, adapter="mock")
    r2 = collect_for_run(
        db_session,
        run_id=run2.id,
        competitors=competitors,
        adapter=adapter,
        period_days=90,
        now=NOW,
    )
    assert r2.posts_inserted == 0
    assert PostRepo(db_session).count_all() == total_after_first


def test_period_days_changes_the_window(db_session):
    competitors = _competitors(db_session)
    adapter = MockAdapter(now=NOW)

    run_week = RunRepo(db_session).create(period_days=7, adapter="mock")
    week = collect_for_run(
        db_session,
        run_id=run_week.id,
        competitors=competitors,
        adapter=adapter,
        period_days=7,
        now=NOW,
    )
    # fresh DB per test, so counts reflect only this run
    cutoff = NOW - timedelta(days=7)
    for post in PostRepo(db_session).list_for_competitor(competitors[0].id):
        assert post.posted_at >= cutoff

    run_full = RunRepo(db_session).create(period_days=90, adapter="mock")
    full = collect_for_run(
        db_session,
        run_id=run_full.id,
        competitors=competitors,
        adapter=adapter,
        period_days=90,
        now=NOW,
    )
    assert full.posts_inserted > week.posts_inserted


class _HalfBrokenAdapter(DataSource):
    name = "halfbroken"

    def fetch_company_profile(self, linkedin_url: str) -> CompanyProfile:
        if "pangolin" in linkedin_url:
            raise RuntimeError("scrape blew up")
        return CompanyProfile(name="ok", linkedin_url=linkedin_url, followers=1234)

    def fetch_posts(self, linkedin_url: str, since):
        return [RawPost(url=f"{linkedin_url}#p1", posted_at=datetime(2026, 8, 20), content="hi #x")]


def test_one_competitor_failure_does_not_abort_run(db_session):
    competitors = _competitors(db_session)
    run = RunRepo(db_session).create(period_days=30, adapter="halfbroken")
    result = collect_for_run(
        db_session,
        run_id=run.id,
        competitors=competitors,
        adapter=_HalfBrokenAdapter(),
        period_days=30,
        now=NOW,
    )
    assert result.profiles_collected == 1
    assert len(result.failures) == 1
    assert "Pangolin" in result.failures[0].error

    run_row = RunRepo(db_session).get(run.id)
    assert run_row.error is not None
    assert "scrape blew up" in run_row.error
    # the healthy competitor's post still landed
    assert PostRepo(db_session).count_for_run(run.id) == 1
