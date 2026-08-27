"""Pydantic schema registry.

Every LLM output schema is registered here by name so prompt YAML metadata
(`output_schema: <Name>`) can resolve to the class at load time.
"""

from pydantic import BaseModel

SCHEMA_REGISTRY: dict[str, type[BaseModel]] = {}


def register_schema(cls: type[BaseModel]) -> type[BaseModel]:
    name = cls.__name__
    existing = SCHEMA_REGISTRY.get(name)
    if existing is not None and existing is not cls:
        raise ValueError(f"Schema name collision: {name}")
    SCHEMA_REGISTRY[name] = cls
    return cls


@register_schema
class EchoResult(BaseModel):
    """Example schema used by the prompts/example/echo prompt and tests."""

    message: str
    language: str


# Import side-effect: registers every downstream output schema so prompt YAML metadata
# (``output_schema: <Name>``) resolves at PromptRegistry load time.
from app.schemas import analysis as _analysis  # noqa: E402,F401
from app.schemas import intelligence as _intelligence  # noqa: E402,F401
from app.schemas import strategy as _strategy  # noqa: E402,F401
from app.schemas import strategy_map as _strategy_map  # noqa: E402,F401
