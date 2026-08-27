"""APScheduler wiring for recurring runs (EPIC-08).

An ``AsyncIOScheduler`` started with the FastAPI lifespan. Jobs are the ``schedules``
rows; each fires ``_fire`` which — unless a run is already in progress (overlap guard) —
creates a ``trigger='scheduled'`` run and executes the full pipeline in a worker thread.
The pipeline's own loop step then diffs against the previous run.

``cron`` is a standard 5-field crontab expression, or ``@every <n>s`` (interval, mainly
for tests / tight cadences).
"""

from __future__ import annotations

import anyio
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

from app.core.logging import get_logger
from app.datasources.base import get_datasource
from app.db.models import Schedule
from app.db.repos import CompetitorRepo, RunRepo, ScheduleRepo
from app.pipeline import run_pipeline

log = get_logger(__name__)


class InvalidCronError(ValueError):
    pass


def make_trigger(cron: str):
    cron = cron.strip()
    if cron.startswith("@every "):
        raw = cron.split(None, 1)[1].strip().rstrip("s")
        try:
            seconds = float(raw)
        except ValueError as exc:
            raise InvalidCronError(f"bad interval {cron!r}") from exc
        if seconds <= 0:
            raise InvalidCronError("interval must be positive")
        return IntervalTrigger(seconds=seconds)
    try:
        return CronTrigger.from_crontab(cron)
    except ValueError as exc:
        raise InvalidCronError(f"invalid cron expression {cron!r}: {exc}") from exc


def validate_cron(cron: str) -> None:
    make_trigger(cron)


class SchedulerService:
    def __init__(self, session_factory, scheduler: AsyncIOScheduler | None = None) -> None:
        self.session_factory = session_factory
        self.scheduler = scheduler or AsyncIOScheduler()

    # -- lifecycle --------------------------------------------------- #
    def start(self) -> None:
        session = self.session_factory()
        try:
            for sched in ScheduleRepo(session).list_all(enabled_only=True):
                self._add_job(sched)
        finally:
            session.close()
        if not self.scheduler.running:
            self.scheduler.start()
        log.info("scheduler_started", jobs=len(self.scheduler.get_jobs()))

    def shutdown(self, wait: bool = False) -> None:
        if self.scheduler.running:
            self.scheduler.shutdown(wait=wait)

    # -- job management -------------------------------------------- #
    def _job_id(self, schedule_id: int) -> str:
        return f"schedule-{schedule_id}"

    def _add_job(self, sched: Schedule) -> None:
        self.scheduler.add_job(
            self._fire,
            make_trigger(sched.cron),
            args=[sched.id],
            id=self._job_id(sched.id),
            replace_existing=True,
            max_instances=1,
            coalesce=True,
        )

    def sync_schedule(self, sched: Schedule) -> None:
        """Add / replace / remove a job to match a schedule row."""
        job_id = self._job_id(sched.id)
        existing = self.scheduler.get_job(job_id)
        if sched.enabled:
            self._add_job(sched)
        elif existing:
            self.scheduler.remove_job(job_id)

    def remove_schedule(self, schedule_id: int) -> None:
        job = self.scheduler.get_job(self._job_id(schedule_id))
        if job:
            self.scheduler.remove_job(self._job_id(schedule_id))

    def next_run_time(self, schedule_id: int):
        job = self.scheduler.get_job(self._job_id(schedule_id))
        return job.next_run_time if job else None

    # -- the job body -------------------------------------------- #
    async def _fire(self, schedule_id: int) -> None:
        run_id = self._start_scheduled_run(schedule_id)
        if run_id is not None:
            await anyio.to_thread.run_sync(run_pipeline, self.session_factory, run_id)

    def _start_scheduled_run(self, schedule_id: int) -> int | None:
        session = self.session_factory()
        try:
            sched = ScheduleRepo(session).get(schedule_id)
            if sched is None or not sched.enabled:
                return None
            in_progress = RunRepo(session).any_in_progress()
            if in_progress is not None:
                log.info(
                    "scheduled_run_skipped_overlap",
                    schedule_id=schedule_id,
                    active_run=in_progress.id,
                )
                return None
            competitors = CompetitorRepo(session).list_all(status="active")
            if not competitors:
                log.info("scheduled_run_skipped_no_competitors", schedule_id=schedule_id)
                return None
            # surfaces a bad adapter config early
            get_datasource(sched.adapter)
            run = RunRepo(session).create(
                period_days=sched.period_days, adapter=sched.adapter, trigger="scheduled"
            )
            ScheduleRepo(session).set_last_run(schedule_id, run.id)
            session.commit()
            log.info("scheduled_run_created", schedule_id=schedule_id, run_id=run.id)
            return run.id
        finally:
            session.close()
