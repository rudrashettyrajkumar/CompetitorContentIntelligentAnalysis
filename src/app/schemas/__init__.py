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
