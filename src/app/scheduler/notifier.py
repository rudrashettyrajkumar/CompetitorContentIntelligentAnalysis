"""Notifier interface for change reports (EPIC-08).

Out of scope: real channels (email/Slack). Ships a log-only default; a channel adapter
just implements ``notify``.
"""

from __future__ import annotations

from typing import Protocol

from app.core.logging import get_logger
from app.schemas.loop import ChangeReport, PeriodDiff

log = get_logger(__name__)


class Notifier(Protocol):
    def notify(self, *, diff: PeriodDiff, report: ChangeReport | None) -> None: ...


class LogNotifier:
    """Default: write the headline + narrative to the structured log."""

    def notify(self, *, diff: PeriodDiff, report: ChangeReport | None) -> None:
        log.info(
            "change_report",
            current_run=diff.current_run_id,
            baseline_run=diff.baseline_run_id,
            material_changes=diff.material_change_count(),
            strategy_refresh=diff.strategy_refresh_recommended,
            headline=(report.headline if report else ""),
            narrative=(report.narrative if report else ""),
        )
