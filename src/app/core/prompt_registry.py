"""Loads prompt packs: <name>.yaml (metadata) + <name>.md (Jinja2 template).

Template files contain a system section and a user section separated by a literal
`---USER---` line. See the prompt-authoring skill for conventions.
"""

from dataclasses import dataclass
from pathlib import Path

import yaml
from jinja2 import Environment, StrictUndefined
from pydantic import BaseModel, Field

from app.schemas import SCHEMA_REGISTRY

USER_DELIMITER = "---USER---"
VALID_TIERS = {"fast", "reasoning"}


class PromptError(Exception):
    pass


class PromptMeta(BaseModel):
    name: str
    version: int = Field(ge=1)
    description: str
    model_tier: str
    temperature: float = Field(ge=0.0, le=2.0)
    output_schema: str
    batch: bool = False
    variables: list[str]


@dataclass(frozen=True)
class PromptSpec:
    meta: PromptMeta
    system_template: str
    user_template: str
    schema: type[BaseModel]


@dataclass(frozen=True)
class RenderedPrompt:
    system: str
    user: str
    meta: PromptMeta
    schema: type[BaseModel]


class PromptRegistry:
    def __init__(
        self,
        prompts_dir: Path,
        schema_registry: dict[str, type[BaseModel]] | None = None,
    ) -> None:
        self.prompts_dir = prompts_dir
        self.schema_registry = schema_registry if schema_registry is not None else SCHEMA_REGISTRY
        self._env = Environment(undefined=StrictUndefined, autoescape=False)
        self._specs: dict[str, PromptSpec] = {}
        self._load_all()

    def _load_all(self) -> None:
        for yaml_path in sorted(self.prompts_dir.rglob("*.yaml")):
            self._load_pair(yaml_path)

    def _load_pair(self, yaml_path: Path) -> None:
        with open(yaml_path, encoding="utf-8") as f:
            raw = yaml.safe_load(f)
        try:
            meta = PromptMeta.model_validate(raw)
        except Exception as exc:
            raise PromptError(f"Invalid prompt metadata in {yaml_path}: {exc}") from exc

        if meta.name != yaml_path.stem:
            raise PromptError(f"{yaml_path}: metadata name {meta.name!r} must equal filename stem")
        if meta.name in self._specs:
            raise PromptError(f"Duplicate prompt name {meta.name!r} ({yaml_path})")
        if meta.model_tier not in VALID_TIERS:
            raise PromptError(f"{yaml_path}: model_tier must be one of {sorted(VALID_TIERS)}")

        md_path = yaml_path.with_suffix(".md")
        if not md_path.exists():
            raise PromptError(f"Missing template {md_path} for prompt {meta.name!r}")
        body = md_path.read_text(encoding="utf-8")
        if USER_DELIMITER not in body:
            raise PromptError(f"{md_path}: missing {USER_DELIMITER!r} delimiter")
        system_template, user_template = (part.strip() for part in body.split(USER_DELIMITER, 1))

        schema = self.schema_registry.get(meta.output_schema)
        if schema is None:
            raise PromptError(
                f"{yaml_path}: output_schema {meta.output_schema!r} is not a registered schema"
            )
        self._specs[meta.name] = PromptSpec(meta, system_template, user_template, schema)

    def names(self) -> list[str]:
        return sorted(self._specs)

    def get(self, name: str) -> PromptSpec:
        try:
            return self._specs[name]
        except KeyError:
            raise PromptError(f"Unknown prompt {name!r}. Known: {self.names()}") from None

    def render(self, name: str, **variables) -> RenderedPrompt:
        spec = self.get(name)
        declared = set(spec.meta.variables)
        provided = set(variables)
        if missing := declared - provided:
            raise PromptError(f"Prompt {name!r}: missing variables {sorted(missing)}")
        if extra := provided - declared:
            raise PromptError(f"Prompt {name!r}: undeclared variables {sorted(extra)}")
        system = self._env.from_string(spec.system_template).render(**variables)
        user = self._env.from_string(spec.user_template).render(**variables)
        return RenderedPrompt(system=system, user=user, meta=spec.meta, schema=spec.schema)
