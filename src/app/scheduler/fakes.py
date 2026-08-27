"""Deterministic FakeLLM responder for the change_report prompt (EPIC-08)."""

from __future__ import annotations

import re

from app.core.model_router import FakeLLM
from app.schemas.loop import ChangeReport


def _change_report_responder(_system: str, user: str) -> dict:
    m = re.search(r"current run (\d+)", user)
    b = re.search(r"baseline run (\d+)", user)
    new_kw = "'emerging'" in user or "emerging_keywords" in user
    return ChangeReport(
        headline="Competitor activity shifted this period"
        if "new_campaigns" in user
        else "Steady period, minor movement",
        narrative=(
            f"Comparing run {m.group(1) if m else '?'} against {b.group(1) if b else '?'}: "
            f"post volume and campaign mix moved. "
            + ("New keywords are gaining share — brief the team to respond. " if new_kw else "")
            + "Recommend a review of the affected pillars."
        ),
    ).model_dump()


def register_loop_fakes(fake_llm: FakeLLM) -> None:
    fake_llm.register(ChangeReport, _change_report_responder)
