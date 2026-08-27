"""End-to-end demo entrypoint (`make demo`).

Scope through EPIC-04: ingest the sample workbook, run a collect-only run with the mock
adapter, run the LangGraph classification subgraph, then the analysis stage
(``score -> rank -> detect_campaigns``). Later epics extend this to strategy. Fully
offline — FakeLLM + FakeCampaignAgent, no network.

The demo rebuilds its SQLite database each run so the schema always matches the code.
"""

from __future__ import annotations

from app.analysis.graph import analyze_run
from app.analysis.mapping_fakes import register_mapping_fakes
from app.analysis.mapping_graph import map_strategy_run
from app.config.settings import (
    PROJECT_ROOT,
    PROMPTS_DIR,
    get_app_config,
    get_models_config,
    get_settings,
)
from app.core.logging import configure_logging, get_logger
from app.core.model_router import FakeLLM, ModelRouter
from app.core.prompt_registry import PromptRegistry
from app.datasources.base import get_datasource, resolve_period_days
from app.datasources.collector import collect_for_run
from app.db.engine import build_engine, build_session_factory, init_db
from app.db.models import Base
from app.db.repos import (
    CampaignRepo,
    CompetitorRepo,
    PostIntelligenceRepo,
    ProfileRepo,
    RunRepo,
)
from app.input.excel import ingest_excel
from app.intelligence.fakes import register_classification_fakes
from app.intelligence.graph import classify_posts_for_run

SAMPLE_XLSX = PROJECT_ROOT / "data" / "input" / "sample_competitors.xlsx"


def main() -> None:
    settings = get_settings()
    app_config = get_app_config()
    configure_logging(settings.log_level, json_output=False)
    log = get_logger("demo")

    engine = build_engine(settings.database_url)
    Base.metadata.drop_all(engine)  # deterministic, schema-fresh demo run
    init_db(engine)
    session = build_session_factory(engine)()

    report = ingest_excel(SAMPLE_XLSX)
    log.info(
        "ingested",
        accepted=report.accepted_count,
        rejected=report.rejected_count,
        warnings=len(report.warnings),
    )
    competitor_repo = CompetitorRepo(session)
    for competitor in report.accepted:
        competitor_repo.upsert(
            name=competitor.name,
            linkedin_url=competitor.linkedin_url,
            industry=competitor.industry,
            market=competitor.market,
            priority=competitor.priority,
        )
    session.commit()

    competitors = competitor_repo.list_all(status="active")
    period_days = resolve_period_days(None, app_config)
    adapter = get_datasource("mock", settings, app_config)

    run_repo = RunRepo(session)
    run = run_repo.create(period_days=period_days, adapter=adapter.name)
    result = collect_for_run(
        session,
        run_id=run.id,
        competitors=competitors,
        adapter=adapter,
        period_days=period_days,
    )
    session.commit()

    # --- EPIC-03: classification subgraph over the collected posts (offline FakeLLM) ---
    registry = PromptRegistry(PROMPTS_DIR)
    fake_llm = FakeLLM()
    register_classification_fakes(fake_llm)
    register_mapping_fakes(fake_llm)
    router = ModelRouter(settings, get_models_config(), fake_llm=fake_llm)
    classify = classify_posts_for_run(session, run_id=run.id, router=router, registry=registry)
    session.commit()

    # --- EPIC-04: score -> rank -> detect_campaigns (offline FakeCampaignAgent) ---
    analysis = analyze_run(session, run_id=run.id, router=router, registry=registry)
    session.commit()

    # --- EPIC-05: profiles -> cross -> top_content (offline mapping fakes) ---
    mapping = map_strategy_run(session, run_id=run.id, router=router, registry=registry)
    run_repo.finish(run.id)
    session.commit()

    profile_repo = ProfileRepo(session)
    pi_repo = PostIntelligenceRepo(session)
    intel_rows = pi_repo.list_for_run(run.id)
    fmt_mix = _tally(row.format for row in intel_rows)
    topic_mix = _tally(row.topic for row in intel_rows)
    tfidf_terms = sum(
        1 for row in intel_rows for kw in (row.keywords or []) if kw.get("source") == "tfidf"
    )

    print("\nEPIC-04 demo — ingest + collect + classify + score + campaigns")
    print(f"  competitors ingested : {report.accepted_count}")
    print(f"  run id / period      : {run.id} / {period_days}d  (adapter={adapter.name})")
    print(f"  profiles collected   : {result.profiles_collected}")
    print(f"  posts inserted       : {result.posts_inserted}")
    for r in result.per_competitor:
        prof = profile_repo.get(r.competitor_id)
        followers = prof.followers if prof else None
        status = "ok" if r.ok else f"FAILED: {r.error}"
        print(f"    - {r.name:<26} posts={r.posts_inserted:<3} followers={followers} {status}")
    print(f"  posts classified     : {classify.posts_classified} / {classify.posts_total}")
    print(f"  cache hits           : {classify.cache_hits}")
    print(f"  classify errors      : {len(classify.errors)}")
    print(f"  tfidf keywords merged: {tfidf_terms}")
    print(f"  format mix           : {fmt_mix}")
    print(f"  topic mix            : {topic_mix}")

    print(f"  posts scored         : {analysis.score.posts_scored}")
    print(f"  with engagement rate : {analysis.score.with_rate}")
    print(f"  incomplete metrics   : {analysis.score.incomplete_metrics}")
    top = analysis.rankings.top_posts[:3]
    for tp in top:
        rate = f"{tp.engagement_rate:.2f}%" if tp.engagement_rate is not None else "n/a"
        print(f"    top post  score={tp.engagement_score:<9.0f} rate={rate:<7} {tp.url}")
    print("  format performance   : Format | Posts | Avg engagement | Best post")
    for fp in analysis.rankings.top_formats[:5]:
        print(f"    {fp.format:<20} {fp.posts:<5} {fp.avg_engagement:<14.0f} {fp.best_post}")
    print(f"  campaigns proposed   : {analysis.campaigns.proposed}")
    print(f"  campaigns persisted  : {analysis.campaigns.persisted}")
    print(f"  campaigns dropped    : {len(analysis.campaigns.dropped)}")
    for row in CampaignRepo(session).list_for_run(run.id)[:5]:
        print(
            f"    - {row.name:<40} posts={len(row.post_ids or []):<3} "
            f"engagement={row.total_engagement:.0f}"
        )

    print(f"  strategy profiles    : {len(mapping.profiles.profiles)}")
    for prof in mapping.profiles.profiles:
        print(
            f"    - {prof.competitor:<26} themes={prof.primary_themes} "
            f"best_fmt={prof.best_format} freq={prof.posting_frequency_per_week}/wk "
            f"windows={prof.engagement_windows}"
        )
    ci = mapping.cross.insights
    print(f"  common themes        : {[t.topic for t in ci.common_themes]}")
    print(f"  white spaces         : {[(w.topic, w.reason) for w in ci.white_spaces][:6]}")
    print(
        f"  format opportunities : "
        f"{[(f.format, f.engagement_multiplier) for f in ci.format_opportunities]}"
    )
    print(f"  keyword matrix       : {[(k.term, k.quadrant) for k in ci.keyword_matrix][:8]}")
    tc = mapping.top_content.report
    print(f"  top content ({tc.ranked_by}) : {len(tc.items)} rows")
    for it in tc.items[:3]:
        print(f"    #{it.rank} {it.competitor:<22} {it.why.summary}")

    reclassify = classify_posts_for_run(session, run_id=run.id, router=router, registry=registry)
    session.commit()
    print(f"  re-run reclassified  : {reclassify.posts_classified} (expect 0 — cache)")

    session.close()
    engine.dispose()


def _tally(values) -> dict[str, int]:
    counts: dict[str, int] = {}
    for value in values:
        counts[value] = counts.get(value, 0) + 1
    return dict(sorted(counts.items(), key=lambda kv: -kv[1]))


if __name__ == "__main__":
    main()
