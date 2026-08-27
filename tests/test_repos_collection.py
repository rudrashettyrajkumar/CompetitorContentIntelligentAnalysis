from datetime import datetime

from app.db.repos import CompetitorRepo, PostRepo, ProfileRepo
from app.schemas.collection import CompanyProfile, RawPost


def _competitor(session):
    return CompetitorRepo(session).upsert(
        name="Acme", linkedin_url="https://www.linkedin.com/company/acme"
    )


def test_profile_repo_upserts_in_place(db_session):
    c = _competitor(db_session)
    repo = ProfileRepo(db_session)
    first = repo.upsert(c.id, CompanyProfile(name="Acme", followers=100, services=["a"]))
    second = repo.upsert(c.id, CompanyProfile(name="Acme", followers=250, services=["a", "b"]))
    assert first.id == second.id
    assert repo.get(c.id).followers == 250
    assert repo.get(c.id).services == ["a", "b"]


def test_post_repo_dedupes_on_url(db_session):
    c = _competitor(db_session)
    repo = PostRepo(db_session)
    posts = [
        RawPost(url="https://li/1", posted_at=datetime(2026, 8, 1), content="a #x"),
        RawPost(url="https://li/2", posted_at=datetime(2026, 8, 2), content="b #y"),
        RawPost(url="https://li/2", posted_at=datetime(2026, 8, 2), content="dupe in batch"),
    ]
    inserted = repo.insert_new(run_id=1, competitor_id=c.id, posts=posts, source_adapter="mock")
    assert len(inserted) == 2

    again = repo.insert_new(
        run_id=2,
        competitor_id=c.id,
        posts=[RawPost(url="https://li/1", posted_at=datetime(2026, 8, 1), content="a #x")],
        source_adapter="mock",
    )
    assert again == []
    assert repo.count_all() == 2
    assert repo.list_for_competitor(c.id)[0].source_adapter == "mock"


def test_post_repo_empty_input(db_session):
    c = _competitor(db_session)
    assert (
        PostRepo(db_session).insert_new(
            run_id=1, competitor_id=c.id, posts=[], source_adapter="mock"
        )
        == []
    )
