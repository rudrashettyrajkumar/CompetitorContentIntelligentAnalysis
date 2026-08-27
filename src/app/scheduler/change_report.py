"""Generate the change-report narrative from a PeriodDiff (EPIC-08)."""

from __future__ import annotations

from app.core.logging import get_logger
from app.core.model_router import LLMError, ModelRouter
from app.core.prompt_registry import PromptRegistry
from app.schemas.loop import ChangeReport, PeriodDiff

log = get_logger(__name__)

PROMPT = "change_report"


def generate_change_report(
    diff: PeriodDiff, *, router: ModelRouter, registry: PromptRegistry
) -> ChangeReport:
    rendered = registry.render(PROMPT, diff=diff.model_dump(mode="json"))
    try:
        result = router.invoke(
            tier=rendered.meta.model_tier,
            system=rendered.system,
            user=rendered.user,
            schema=rendered.schema,
            temperature=rendered.meta.temperature,
            prompt_name=rendered.meta.name,
            prompt_version=rendered.meta.version,
        )
        if isinstance(result, ChangeReport):
            return result
    except LLMError as exc:
        log.warning("change_report_failed", error=str(exc))

    # deterministic fallback so a report always exists
    bits = []
    if diff.new_campaigns:
        bits.append(f"{len(diff.new_campaigns)} new campaign(s)")
    if diff.emerging_keywords:
        bits.append(f"{len(diff.emerging_keywords)} emerging keyword(s)")
    if diff.topic_performance_shifts:
        bits.append(f"{len(diff.topic_performance_shifts)} topic shift(s)")
    headline = "Quiet period" if not bits else "Notable movement: " + ", ".join(bits)
    return ChangeReport(
        headline=headline,
        narrative=(
            f"Run {diff.current_run_id} vs {diff.baseline_run_id}: {diff.new_posts} new posts "
            f"({diff.posts_delta_pct:+.1f}%). "
            + ("; ".join(bits) + "." if bits else "No material shifts.")
        ),
    )
