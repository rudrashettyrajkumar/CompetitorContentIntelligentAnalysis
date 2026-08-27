"""The ``collect`` stage — callable standalone or as the first pipeline node.

For each competitor: fetch the company profile, upsert it, fetch posts for the
period, insert the new ones (dedup on URL). A single competitor's adapter failure is
recorded against the run and does not abort the others.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from app.core.logging import get_logger
from app.datasources.base import DataSource
from app.db.models import Competitor
from app.db.repos import PostRepo, ProfileRepo, RunRepo

log = get_logger(__name__)


@dataclass
class CompetitorCollectionResult:
    competitor_id: int
    name: str
    ok: bool
    posts_seen: int = 0
    posts_inserted: int = 0
    error: str | None = None


@dataclass
class CollectionResult:
    run_id: int
    period_days: int
    adapter: str
    since: datetime
    per_competitor: list[CompetitorCollectionResult] = field(default_factory=list)

    @property
    def profiles_collected(self) -> int:
        return sum(1 for r in self.per_competitor if r.ok)

    @property
    def posts_inserted(self) -> int:
        return sum(r.posts_inserted for r in self.per_competitor)

    @property
    def failures(self) -> list[CompetitorCollectionResult]:
        return [r for r in self.per_competitor if not r.ok]


def collect_for_run(
    session: Session,
    *,
    run_id: int,
    competitors: list[Competitor],
    adapter: DataSource,
    period_days: int,
    now: datetime | None = None,
) -> CollectionResult:
    now = now or datetime.utcnow()
    since = now - timedelta(days=period_days)
    run_repo = RunRepo(session)
    profile_repo = ProfileRepo(session)
    post_repo = PostRepo(session)

    run_repo.set_stage(run_id, "collect")
    result = CollectionResult(
        run_id=run_id, period_days=period_days, adapter=adapter.name, since=since
    )

    for competitor in competitors:
        log_ctx = dict(run_id=run_id, competitor=competitor.name, adapter=adapter.name)
        try:
            profile = adapter.fetch_company_profile(competitor.linkedin_url)
            profile_repo.upsert(competitor.id, profile)

            posts = adapter.fetch_posts(competitor.linkedin_url, since)
            inserted = post_repo.insert_new(
                run_id=run_id,
                competitor_id=competitor.id,
                posts=posts,
                source_adapter=adapter.name,
            )
            result.per_competitor.append(
                CompetitorCollectionResult(
                    competitor_id=competitor.id,
                    name=competitor.name,
                    ok=True,
                    posts_seen=len(posts),
                    posts_inserted=len(inserted),
                )
            )
            log.info("collected", **log_ctx, posts_seen=len(posts), posts_inserted=len(inserted))
        except Exception as exc:  # noqa: BLE001 — one competitor must not sink the run
            message = f"{competitor.name}: {type(exc).__name__}: {exc}"
            run_repo.append_error(run_id, message)
            result.per_competitor.append(
                CompetitorCollectionResult(
                    competitor_id=competitor.id,
                    name=competitor.name,
                    ok=False,
                    error=message,
                )
            )
            log.warning("collect_failed", **log_ctx, error=str(exc))

    return result
