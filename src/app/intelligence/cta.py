"""CTA extraction node (brief step 6): primary call-to-action type + verbatim text."""

from __future__ import annotations

from collections.abc import Sequence

from app.config.settings import Taxonomies
from app.core.model_router import ModelRouter
from app.core.prompt_registry import PromptRegistry
from app.intelligence._llm import invoke_prompt, posts_payload
from app.intelligence.batching import PostItem, run_in_batches

PROMPT = "cta_extract"


def classify_ctas(
    items: Sequence[PostItem],
    *,
    router: ModelRouter,
    registry: PromptRegistry,
    taxonomies: Taxonomies,
    batch_size: int,
) -> tuple[dict[int, tuple[str, str | None]], dict[int, str]]:
    """Return ``({index: (cta, cta_text)}, {index: error})``."""

    def call(batch: list[PostItem]) -> dict[int, tuple[str, str | None]]:
        result = invoke_prompt(
            registry,
            router,
            PROMPT,
            posts=posts_payload(batch),
            taxonomy=taxonomies.cta_types,
        )
        return {r.index: (r.cta, r.cta_text) for r in result.results}

    return run_in_batches(items, batch_size=batch_size, call=call, task="cta")
