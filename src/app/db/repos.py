"""Repositories own every query. Feature code never touches SQLAlchemy directly.

EPIC-01 ships CompetitorRepo and RunRepo; later epics extend this module.
"""

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Competitor, Run


class CompetitorRepo:
    def __init__(self, session: Session) -> None:
        self.session = session

    def upsert(self, **fields) -> Competitor:
        """Insert or update by canonical linkedin_url."""
        url = fields["linkedin_url"]
        existing = self.session.scalar(select(Competitor).where(Competitor.linkedin_url == url))
        if existing:
            for key, value in fields.items():
                setattr(existing, key, value)
            self.session.flush()
            return existing
        competitor = Competitor(**fields)
        self.session.add(competitor)
        self.session.flush()
        return competitor

    def get(self, competitor_id: int) -> Competitor | None:
        return self.session.get(Competitor, competitor_id)

    def list_all(self, status: str | None = "active") -> list[Competitor]:
        stmt = select(Competitor).order_by(Competitor.name)
        if status:
            stmt = stmt.where(Competitor.status == status)
        return list(self.session.scalars(stmt))

    def delete(self, competitor_id: int) -> bool:
        competitor = self.get(competitor_id)
        if competitor is None:
            return False
        self.session.delete(competitor)
        self.session.flush()
        return True


class RunRepo:
    def __init__(self, session: Session) -> None:
        self.session = session

    def create(self, *, period_days: int, adapter: str) -> Run:
        run = Run(period_days=period_days, adapter=adapter, status="pending")
        self.session.add(run)
        self.session.flush()
        return run

    def get(self, run_id: int) -> Run | None:
        return self.session.get(Run, run_id)

    def list_all(self) -> list[Run]:
        return list(self.session.scalars(select(Run).order_by(Run.started_at.desc())))

    def set_stage(self, run_id: int, stage: str) -> None:
        run = self.session.get(Run, run_id)
        if run is None:
            raise ValueError(f"Unknown run {run_id}")
        run.stage = stage
        run.status = "running"
        self.session.flush()

    def finish(self, run_id: int, *, error: str | None = None) -> None:
        run = self.session.get(Run, run_id)
        if run is None:
            raise ValueError(f"Unknown run {run_id}")
        run.status = "failed" if error else "completed"
        run.error = error
        run.finished_at = datetime.utcnow()
        self.session.flush()
