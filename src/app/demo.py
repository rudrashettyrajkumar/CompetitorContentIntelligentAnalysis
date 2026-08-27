"""End-to-end demo entrypoint (`make demo`).

EPIC-02 scope: ingest the sample workbook, then run a collect-only run with the mock
adapter. Later epics extend this to the full classification/analysis/strategy pipeline.
Fully offline — no LLM calls, no network.
"""

from __future__ import annotations

from app.config.settings import PROJECT_ROOT, get_app_config, get_settings
from app.core.logging import configure_logging, get_logger
from app.datasources.base import get_datasource, resolve_period_days
from app.datasources.collector import collect_for_run
from app.db.engine import build_engine, build_session_factory, init_db
from app.db.repos import CompetitorRepo, ProfileRepo, RunRepo
from app.input.excel import ingest_excel

SAMPLE_XLSX = PROJECT_ROOT / "data" / "input" / "sample_competitors.xlsx"


def main() -> None:
    settings = get_settings()
    app_config = get_app_config()
    configure_logging(settings.log_level, json_output=False)
    log = get_logger("demo")

    engine = build_engine(settings.database_url)
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
    run_repo.finish(run.id)
    session.commit()

    profile_repo = ProfileRepo(session)
    print("\nEPIC-02 demo — ingest + collect")
    print(f"  competitors ingested : {report.accepted_count}")
    print(f"  run id / period      : {run.id} / {period_days}d  (adapter={adapter.name})")
    print(f"  profiles collected   : {result.profiles_collected}")
    print(f"  posts inserted       : {result.posts_inserted}")
    for r in result.per_competitor:
        prof = profile_repo.get(r.competitor_id)
        followers = prof.followers if prof else None
        status = "ok" if r.ok else f"FAILED: {r.error}"
        print(f"    - {r.name:<26} posts={r.posts_inserted:<3} followers={followers} {status}")
    session.close()
    engine.dispose()


if __name__ == "__main__":
    main()
