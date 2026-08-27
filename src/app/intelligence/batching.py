"""Batch-with-fallback runner shared by every classification task.

Quota economy (solution-design §4.2): one LLM call classifies up to ``batch_size``
posts. If a batch call fails — transport error, unrepairable schema output, or a partial
response missing some posts — it is retried once as individual per-post calls before the
still-failing posts are recorded as errors. One competitor's bad post never sinks the
run.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass, field

from app.core.logging import get_logger
from app.core.model_router import LLMError

log = get_logger(__name__)


@dataclass(frozen=True)
class PostItem:
    """One post as seen by the classification nodes (batch position = ``index``)."""

    post_id: int
    index: int
    content: str
    media_type: str
    hashtags: list[str] = field(default_factory=list)


class BatchIncompleteError(LLMError):
    """A batch call returned but omitted results for some posts."""


def run_in_batches(
    items: Sequence[PostItem],
    *,
    batch_size: int,
    call: Callable[[list[PostItem]], dict[int, object]],
    task: str,
) -> tuple[dict[int, object], dict[int, str]]:
    """Run ``call`` over ``items`` in batches, keyed by ``PostItem.index``.

    Returns ``(results_by_index, errors_by_index)``.
    """
    results: dict[int, object] = {}
    errors: dict[int, str] = {}
    batch_size = max(1, batch_size)

    for start in range(0, len(items), batch_size):
        batch = list(items[start : start + batch_size])
        try:
            got = call(batch)
            missing = [it for it in batch if it.index not in got]
            if missing:
                raise BatchIncompleteError(
                    f"{task}: batch of {len(batch)} omitted {len(missing)} results"
                )
            results.update(got)
        except (LLMError, ValueError) as exc:
            log.warning(
                "batch_failed_fallback_per_post", task=task, size=len(batch), error=str(exc)
            )
            for item in batch:
                try:
                    single = call([item])
                    if item.index not in single:
                        raise BatchIncompleteError(f"{task}: no result for post index {item.index}")
                    results[item.index] = single[item.index]
                except (LLMError, ValueError) as exc2:  # noqa: PERF203 — per-post isolation is intentional
                    errors[item.index] = f"{type(exc2).__name__}: {exc2}"
                    log.warning("per_post_failed", task=task, index=item.index, error=str(exc2))

    return results, errors
