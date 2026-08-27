"""Thin glue between the classification nodes and the prompt/router stack.

Every classification LLM call in EPIC-03 goes through ``invoke_prompt`` so tier,
temperature and version tagging stay consistent and never leak into feature code.
"""

from __future__ import annotations

from collections.abc import Sequence

from pydantic import BaseModel

from app.core.model_router import ModelRouter
from app.core.prompt_registry import PromptRegistry
from app.intelligence.batching import PostItem


def posts_payload(batch: Sequence[PostItem]) -> list[dict[str, object]]:
    """Render batch posts as the plain list the prompt templates iterate over."""
    return [{"index": it.index, "content": it.content, "media_type": it.media_type} for it in batch]


def invoke_prompt(
    registry: PromptRegistry,
    router: ModelRouter,
    name: str,
    /,
    **variables: object,
) -> BaseModel:
    rendered = registry.render(name, **variables)
    return router.invoke(
        tier=rendered.meta.model_tier,
        system=rendered.system,
        user=rendered.user,
        schema=rendered.schema,
        temperature=rendered.meta.temperature,
        prompt_name=rendered.meta.name,
        prompt_version=rendered.meta.version,
    )
