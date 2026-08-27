from pathlib import Path

import pytest

from app.core.prompt_registry import PromptError, PromptRegistry
from app.schemas import EchoResult


def test_registry_loads_example_prompt(prompt_registry):
    assert "echo" in prompt_registry.names()
    spec = prompt_registry.get("echo")
    assert spec.meta.model_tier == "fast"
    assert spec.schema is EchoResult


def test_render_substitutes_variables(prompt_registry):
    rendered = prompt_registry.render("echo", message="hello world", language="Spanish")
    assert "hello world" in rendered.user
    assert "Spanish" in rendered.user
    assert rendered.system  # non-empty system section
    assert rendered.schema is EchoResult


def test_render_missing_variable_raises(prompt_registry):
    with pytest.raises(PromptError, match="missing variables"):
        prompt_registry.render("echo", message="hi")


def test_render_undeclared_variable_raises(prompt_registry):
    with pytest.raises(PromptError, match="undeclared variables"):
        prompt_registry.render("echo", message="hi", language="en", extra="nope")


def test_unknown_prompt_raises(prompt_registry):
    with pytest.raises(PromptError, match="Unknown prompt"):
        prompt_registry.get("does-not-exist")


def _write_pair(tmp_path: Path, name: str, yaml_body: str, md_body: str | None) -> Path:
    (tmp_path / f"{name}.yaml").write_text(yaml_body)
    if md_body is not None:
        (tmp_path / f"{name}.md").write_text(md_body)
    return tmp_path


GOOD_YAML = """
name: {name}
version: 1
description: test
model_tier: fast
temperature: 0.1
output_schema: EchoResult
batch: false
variables: [x]
"""


def test_missing_md_file_raises(tmp_path):
    _write_pair(tmp_path, "solo", GOOD_YAML.format(name="solo"), None)
    with pytest.raises(PromptError, match="Missing template"):
        PromptRegistry(tmp_path)


def test_missing_delimiter_raises(tmp_path):
    _write_pair(tmp_path, "nodelim", GOOD_YAML.format(name="nodelim"), "just a system prompt")
    with pytest.raises(PromptError, match="delimiter"):
        PromptRegistry(tmp_path)


def test_name_filename_mismatch_raises(tmp_path):
    _write_pair(tmp_path, "fileA", GOOD_YAML.format(name="other"), "sys\n---USER---\n{{ x }}")
    with pytest.raises(PromptError, match="filename stem"):
        PromptRegistry(tmp_path)


def test_unregistered_schema_raises(tmp_path):
    bad = GOOD_YAML.format(name="badschema").replace("EchoResult", "NoSuchSchema")
    _write_pair(tmp_path, "badschema", bad, "sys\n---USER---\n{{ x }}")
    with pytest.raises(PromptError, match="not a registered schema"):
        PromptRegistry(tmp_path)


def test_invalid_tier_raises(tmp_path):
    bad = GOOD_YAML.format(name="badtier").replace("model_tier: fast", "model_tier: huge")
    _write_pair(tmp_path, "badtier", bad, "sys\n---USER---\n{{ x }}")
    with pytest.raises(PromptError, match="model_tier"):
        PromptRegistry(tmp_path)


def test_all_repo_prompts_valid(prompt_registry):
    """Every prompt pack in prompts/ must load — this test guards future epics."""
    for name in prompt_registry.names():
        spec = prompt_registry.get(name)
        assert spec.meta.description
        assert spec.meta.variables
