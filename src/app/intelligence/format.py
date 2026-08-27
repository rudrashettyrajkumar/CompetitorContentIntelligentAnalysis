"""Format classification node (brief step 5): 17-value content-format taxonomy.

Batched; media type is passed only as a hint — the model decides the intent-format.
"""

from __future__ import annotations

from collections.abc import Sequence

from app.config.settings import Taxonomies
from app.core.model_router import ModelRouter
from app.core.prompt_registry import PromptRegistry
from app.intelligence._llm import invoke_prompt, posts_payload
from app.intelligence.batching import PostItem, run_in_batches

PROMPT = "format_classify"


def classify_formats(
    items: Sequence[PostItem],
    *,
    router: ModelRouter,
    registry: PromptRegistry,
    taxonomies: Taxonomies,
    batch_size: int,
) -> tuple[dict[int, str], dict[int, str]]:
    """Return ``({index: format}, {index: error})`` for every post in ``items``."""

    def call(batch: list[PostItem]) -> dict[int, str]:
        result = invoke_prompt(
            registry,
            router,
            PROMPT,
            posts=posts_payload(batch),
            taxonomy=taxonomies.formats,
        )
        return {r.index: r.format for r in result.results}

    return run_in_batches(items, batch_size=batch_size, call=call, task="format")
