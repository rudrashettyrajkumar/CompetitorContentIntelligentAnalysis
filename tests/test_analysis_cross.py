"""Cross-competitor insights on a seeded fixture with known planted signals (EPIC-05).

Planted, and asserted:
* white space  -> ``industry_4_0`` (no competitor covers it)
* opportunity topic -> ``automation`` (one post, engagement far above the median)
* format opportunity -> ``video`` (17% of posts, ~3x average engagement)
* keyword quadrants -> ``boilerplate`` high-freq/low-perf, ``breakthrough`` low-freq/high-perf
"""

import pytest

from app.analysis.cross import _Row, build_cross_insights, compute_cross_insights
from app.analysis.engagement import score_run
from app.config.settings import get_taxonomies
from app.db.repos import CompetitorRepo, PostIntelligenceRepo, PostRepo, ProfileRepo, RunRepo
from app.schemas.collection import CompanyProfile, RawPost
from app.schemas.intelligence import KeywordTag, PostClassification

_CFG = {
    "common_min_competitors": 2,
    "saturation_min_competitors": 3,
    "whitespace_max_competitors": 1,
    "format_opportunity_multiplier": 2.0,
    "format_opportunity_max_share": 0.25,
    "keyword_min_frequency": 2,
}

# competitor, topic, format, score, keyword
_FIXTURE = [
    ("A", "ai", "text_only", 100, "boilerplate"),
    ("A", "ai", "text_only", 120, "boilerplate"),
    ("A", "cloud", "text_only", 90, "boilerplate"),
    ("A", "cloud", "video", 900, "breakthrough"),
    ("B", "ai", "text_only", 110, "boilerplate"),
    ("B", "ai", "text_only", 95, "boilerplate"),
    ("B", "cybersecurity", "text_only", 105, "boilerplate"),
    ("B", "cybersecurity", "video", 850, "breakthrough"),
    ("C", "ai", "text_only", 100, "boilerplate"),
    ("C", "ai", "text_only", 130, "boilerplate"),
    ("C", "data_analytics", "text_only", 115, "boilerplate"),
    ("C", "automation", "text_only", 800, "breakthrough"),
]


def _rows():
    comp_ids = {name: i for i, name in enumerate(["A", "B", "C"], start=1)}
    return [
        _Row(comp_ids[c], topic, fmt, float(score), [kw]) for c, topic, fmt, score, kw in _FIXTURE
    ]


@pytest.fixture
def insights():
    return compute_cross_insights(_rows(), cfg=_CFG, taxonomy_topics=get_taxonomies().topics)


def test_common_and_saturated_themes(insights):
    assert [t.topic for t in insights.common_themes] == ["ai"]
    assert [t.topic for t in insights.saturated_topics] == ["ai"]
    assert insights.common_themes[0].competitors_covering == 3


def test_planted_white_space_is_found(insights):
    ws = {w.topic: w for w in insights.white_spaces}
    assert "industry_4_0" in ws
    assert ws["industry_4_0"].reason == "low_coverage"
    assert ws["industry_4_0"].competitors_covering == 0
    assert "other" not in ws  # the escape-hatch topic is never a white space


def test_planted_opportunity_topic_is_found(insights):
    topics = {o.topic: o for o in insights.opportunity_topics}
    assert "automation" in topics
    assert topics["automation"].engagement_vs_median > 0
    assert topics["automation"].coverage_vs_median < 0


def test_planted_format_opportunity_is_found(insights):
    fmts = {f.format: f for f in insights.format_opportunities}
    assert "video" in fmts
    assert fmts["video"].engagement_multiplier >= 2.0
    assert fmts["video"].post_share == pytest.approx(2 / 12, abs=1e-3)
    assert "text_only" not in fmts  # the workhorse format is not an "opportunity"


def test_keyword_matrix_quadrants(insights):
    q = {k.term: k.quadrant for k in insights.keyword_matrix}
    assert q["boilerplate"] == "high_freq_low_perf"
    assert q["breakthrough"] == "low_freq_high_perf"


def test_thresholds_are_configurable():
    strict = dict(_CFG, format_opportunity_multiplier=5.0)
    out = compute_cross_insights(_rows(), cfg=strict, taxonomy_topics=get_taxonomies().topics)
    assert [f.format for f in out.format_opportunities] == []  # 3x no longer clears 5x

    loose = dict(_CFG, common_min_competitors=1)
    out2 = compute_cross_insights(_rows(), cfg=loose, taxonomy_topics=get_taxonomies().topics)
    assert len(out2.common_themes) > 1  # cloud, cybersecurity, ... now count as common


def test_build_cross_insights_over_db(db_session):
    comps = {
        name: CompetitorRepo(db_session).upsert(
            name=name, linkedin_url=f"https://www.linkedin.com/company/{name.lower()}"
        )
        for name in ["A", "B", "C"]
    }
    for c in comps.values():
        ProfileRepo(db_session).upsert(c.id, CompanyProfile(followers=10_000))
    run = RunRepo(db_session).create(period_days=30, adapter="mock")
    for i, (cname, topic, fmt, score, kw) in enumerate(_FIXTURE):
        created = PostRepo(db_session).insert_new(
            run_id=run.id,
            competitor_id=comps[cname].id,
            source_adapter="mock",
            posts=[
                RawPost(
                    url=f"https://example.test/x{i}",
                    posted_at=__import__("datetime").datetime(2026, 1, 1 + i, 9),
                    content=f"post {i}",
                    media_type="text",
                    reactions=score,
                    comments=0,
                    reposts=0,
                )
            ],
        )
        PostIntelligenceRepo(db_session).upsert(
            created[0].id,
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
    db_session.commit()
    score_run(db_session, run_id=run.id)
    db_session.commit()

    result = build_cross_insights(db_session, run_id=run.id)
    assert "industry_4_0" in {w.topic for w in result.insights.white_spaces}
    assert "video" in {f.format for f in result.insights.format_opportunities}
    assert RunRepo(db_session).get(run.id).stage == "cross"
