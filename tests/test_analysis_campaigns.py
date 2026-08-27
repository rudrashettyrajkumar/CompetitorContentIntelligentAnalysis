"""Campaign detection: offline stub clustering, URL validation, overlap resolution."""

from datetime import datetime, timedelta

from app.analysis.campaigns import (
    DeepCampaignAgent,
    RunPostRef,
    build_campaign_inputs,
    detect_campaigns_for_run,
    resolve_overlaps,
    validate_campaigns,
)
from app.analysis.engagement import score_run
from app.analysis.fakes import register_campaign_fakes
from app.core.model_router import ModelRouter
from app.db.repos import (
    CampaignRepo,
    CompetitorRepo,
    PostIntelligenceRepo,
    PostRepo,
    ProfileRepo,
    RunRepo,
)
from app.schemas.analysis import CampaignRecord, ValidatedCampaign
from app.schemas.collection import CompanyProfile, RawPost
from app.schemas.intelligence import KeywordTag, PostClassification

BASE = datetime(2026, 3, 1, 9, 0)


def _ref(pid, *, day=0, score=100.0, competitor_id=1, topic="ai", fmt="text_only", cta="none"):
    return RunPostRef(
        post_id=pid,
        competitor_id=competitor_id,
        competitor_name="Acme",
        url=f"https://example.test/p{pid}",
        posted_at=BASE + timedelta(days=day),
        format=fmt,
        topic=topic,
        sub_topic="AI for Manufacturing",
        cta=cta,
        score=score,
        keywords=["ai", "manufacturing"],
        hashtags=["ai"],
    )


def _candidate(refs, name="AI for Manufacturing"):
    return CampaignRecord(
        name=name,
        theme="AI for Manufacturing",
        post_urls=[r.url for r in refs],
        formats=["text_only"],
        keywords=["ai"],
    )


# --------------------------------------------------------------------------- #
# validation
# --------------------------------------------------------------------------- #
def test_valid_cluster_produces_one_campaign_with_recomputed_aggregates():
    refs = [_ref(1, day=0, score=10), _ref(2, day=3, score=90), _ref(3, day=6, score=50)]
    by_url = {r.url: r for r in refs}

    validated, dropped = validate_campaigns(
        [_candidate(refs)], posts_by_url=by_url, window_days=30, min_posts=3
    )

    assert dropped == []
    assert len(validated) == 1
    camp = validated[0]
    assert camp.post_ids == [1, 2, 3]
    assert camp.total_engagement == 150
    assert camp.top_post_id == 2
    assert camp.top_post_url == "https://example.test/p2"
    assert camp.start_date == BASE
    assert camp.end_date == BASE + timedelta(days=6)


def test_campaign_with_unknown_url_is_rejected():
    refs = [_ref(1), _ref(2, day=1), _ref(3, day=2)]
    by_url = {r.url: r for r in refs}
    bogus = CampaignRecord(
        name="Hallucinated",
        theme="ghost",
        post_urls=[refs[0].url, refs[1].url, "https://example.test/DOES-NOT-EXIST"],
    )

    validated, dropped = validate_campaigns(
        [bogus], posts_by_url=by_url, window_days=30, min_posts=3
    )

    assert validated == []
    assert len(dropped) == 1
    assert dropped[0][0] == "Hallucinated"
    assert "unknown post url" in dropped[0][1]


def test_campaign_below_min_posts_is_dropped():
    refs = [_ref(1), _ref(2, day=1), _ref(3, day=2)]
    by_url = {r.url: r for r in refs}
    validated, dropped = validate_campaigns(
        [_candidate(refs[:2])], posts_by_url=by_url, window_days=30, min_posts=3
    )
    assert validated == []
    assert "< 3" in dropped[0][1]


def test_campaign_outside_window_is_dropped():
    refs = [_ref(1, day=0), _ref(2, day=20), _ref(3, day=50)]
    by_url = {r.url: r for r in refs}
    validated, dropped = validate_campaigns(
        [_candidate(refs)], posts_by_url=by_url, window_days=30, min_posts=3
    )
    assert validated == []
    assert "span" in dropped[0][1]


def test_campaign_spanning_two_competitors_is_dropped():
    refs = [
        _ref(1, competitor_id=1),
        _ref(2, competitor_id=1, day=1),
        _ref(3, competitor_id=2, day=2),
    ]
    by_url = {r.url: r for r in refs}
    validated, dropped = validate_campaigns(
        [_candidate(refs)], posts_by_url=by_url, window_days=30, min_posts=3
    )
    assert validated == []
    assert "competitor" in dropped[0][1]


# --------------------------------------------------------------------------- #
# overlap resolution
# --------------------------------------------------------------------------- #
def _validated(name, refs, engagement):
    return ValidatedCampaign(
        competitor_id=1,
        name=name,
        theme=name,
        post_ids=sorted(r.post_id for r in refs),
        post_urls=[r.url for r in refs],
        start_date=min(r.posted_at for r in refs),
        end_date=max(r.posted_at for r in refs),
        formats=["text_only"],
        total_engagement=engagement,
        top_post_id=max(refs, key=lambda r: r.score).post_id,
    )


def test_overlap_keeps_stronger_campaign_and_trims_the_weaker():
    refs = {i: _ref(i, day=i, score=10 * i) for i in range(1, 8)}
    strong = _validated("Strong", [refs[1], refs[2], refs[3], refs[4]], engagement=1000)
    weak = _validated("Weak", [refs[3], refs[4], refs[5], refs[6], refs[7]], engagement=100)

    kept, conflicts = resolve_overlaps([weak, strong], refs_by_id=refs, min_posts=3)

    assert {c.name for c in kept} == {"Strong", "Weak"}
    strong_out = next(c for c in kept if c.name == "Strong")
    weak_out = next(c for c in kept if c.name == "Weak")
    assert strong_out.post_ids == [1, 2, 3, 4]  # untouched — claimed first
    assert weak_out.post_ids == [5, 6, 7]  # ceded 3 & 4, re-finalised
    assert weak_out.total_engagement == 50 + 60 + 70
    assert any(name == "Weak" and "ceded" in reason for name, reason in conflicts)


def test_overlap_drops_campaign_that_falls_below_min_posts():
    refs = {i: _ref(i, day=i, score=10 * i) for i in range(1, 6)}
    strong = _validated("Strong", [refs[1], refs[2], refs[3], refs[4]], engagement=1000)
    weak = _validated("Weak", [refs[3], refs[4], refs[5]], engagement=100)

    kept, conflicts = resolve_overlaps([weak, strong], refs_by_id=refs, min_posts=3)

    assert [c.name for c in kept] == ["Strong"]
    assert any(name == "Weak" and "dropped" in reason for name, reason in conflicts)


# --------------------------------------------------------------------------- #
# full offline stub path (FakeCampaignAgent via detect_campaigns_for_run)
# --------------------------------------------------------------------------- #
def _seed_classified_run(session):
    comp = CompetitorRepo(session).upsert(
        name="Acme", linkedin_url="https://www.linkedin.com/company/acme"
    )
    ProfileRepo(session).upsert(comp.id, CompanyProfile(followers=100_000))
    run = RunRepo(session).create(period_days=30, adapter="mock")

    # 4-post "AI for Manufacturing"-style cluster + 2 unrelated singletons
    plan = [
        ("ai", 0, 40),
        ("ai", 5, 90),
        ("ai", 9, 60),
        ("ai", 12, 30),
        ("cloud", 3, 25),
        ("cybersecurity", 7, 15),
    ]
    ids = []
    for i, (topic, day, reactions) in enumerate(plan):
        created = PostRepo(session).insert_new(
            run_id=run.id,
            competitor_id=comp.id,
            source_adapter="mock",
            posts=[
                RawPost(
                    url=f"https://example.test/post-{i}",
                    posted_at=datetime(2026, 3, 1, 9, 0) + timedelta(days=day),
                    content=f"post {i} about {topic}",
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
                format="thought_leadership",
                topic=topic,
                sub_topic="AI for Manufacturing" if topic == "ai" else None,
                cta="learn_more",
                keywords=[KeywordTag(term=topic, category="industry_term")],
            ),
            hashtags=["ai"] if topic == "ai" else [],
            prompt_versions={"format_classify": 1},
        )
        ids.append(created[0].id)
    session.commit()
    score_run(session, run_id=run.id)
    session.commit()
    return run.id, ids


def test_offline_stub_detects_the_seeded_cluster(db_session, fake_router):
    run_id, ids = _seed_classified_run(db_session)
    ai_ids = ids[:4]

    result = detect_campaigns_for_run(db_session, run_id=run_id, router=fake_router, registry=None)

    assert result.persisted == 1
    assert result.dropped == []
    campaign = CampaignRepo(db_session).list_for_run(run_id)[0]
    assert sorted(campaign.post_ids) == sorted(ai_ids)
    # weights 1/2/3, comments/reposts 0 -> score == reactions
    assert campaign.total_engagement == 40 + 90 + 60 + 30
    assert campaign.top_post_id == ai_ids[1]  # the 90-reaction post
    assert campaign.start_date == datetime(2026, 3, 1, 9, 0)
    assert campaign.end_date == datetime(2026, 3, 1, 9, 0) + timedelta(days=12)


def test_rerun_replaces_the_runs_campaign_set(db_session, fake_router):
    run_id, _ = _seed_classified_run(db_session)
    detect_campaigns_for_run(db_session, run_id=run_id, router=fake_router, registry=None)
    detect_campaigns_for_run(db_session, run_id=run_id, router=fake_router, registry=None)
    assert CampaignRepo(db_session).count_for_run(run_id) == 1


def test_build_campaign_inputs_writes_one_file_per_competitor(db_session):
    run_id, _ = _seed_classified_run(db_session)
    inputs = build_campaign_inputs(db_session, run_id)
    files = inputs.files()
    assert len(files) == 1
    assert next(iter(files)).startswith("competitor_")


def test_deep_agent_falls_back_to_single_router_call(
    db_session, settings, models_config, fake_llm, prompt_registry
):
    """In fake mode chat_model_for() raises, so DeepCampaignAgent must fall through to the
    router's validate/repair invoke path and still return a valid clustering."""
    run_id, ids = _seed_classified_run(db_session)
    register_campaign_fakes(fake_llm)
    router = ModelRouter(settings, models_config, fake_llm=fake_llm, backoff_base=0)

    agent = DeepCampaignAgent(router, prompt_registry)
    inputs = build_campaign_inputs(db_session, run_id)
    proposed = agent.detect(inputs, window_days=30, min_posts=3)

    assert any(c.theme == "ai" for c in proposed)
    assert any(schema == "CampaignClustering" for schema in (c["schema"] for c in fake_llm.calls))
