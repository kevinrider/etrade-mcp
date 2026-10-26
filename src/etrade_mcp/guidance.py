"""Packaged discovery text; request validation remains in the input models."""

from __future__ import annotations

import re
import tomllib
from functools import lru_cache
from importlib.resources import files
from typing import Any

from pydantic import BaseModel, ConfigDict, TypeAdapter

from etrade_mcp.input_schema import inline_input_schema


class GuidanceCatalog(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    tools: list[str]
    models: dict[str, dict[str, str]]


@lru_cache(maxsize=1)
def catalog() -> GuidanceCatalog:
    content = files("etrade_mcp").joinpath("descriptions", "fields.toml").read_text("utf-8")
    return GuidanceCatalog.model_validate(tomllib.loads(content))


@lru_cache(maxsize=64)
def tool_description(name: str) -> str | None:
    # Only names in the packaged catalog can resolve to files. Injected library
    # and test tools continue to use their own descriptions and input models.
    if name not in catalog().tools:
        return None
    return files("etrade_mcp").joinpath("descriptions", f"{name}.md").read_text("utf-8").strip()


def description_examples(description: str) -> list[dict[str, Any]]:
    """JSON fences are complete tool arguments, also advertised as schema examples."""
    adapter = TypeAdapter(dict[str, Any])
    return [
        adapter.validate_json(block)
        for block in re.findall(r"```json\s*\n(.*?)\n```", description, re.DOTALL)
    ]


def describe_fields(schema: dict[str, Any], model_name: str) -> None:
    """Enrich a fresh schema only; fail visibly on stale packaged field references."""
    descriptions = catalog().models[model_name]
    properties: dict[str, Any] = schema.get("properties", {})
    if properties.keys() != descriptions.keys():
        raise ValueError(f"Field guidance does not match {model_name}")
    for name, field in properties.items():
        field["description"] = descriptions[name]


def described_input_schema(name: str, model: type[BaseModel]) -> dict[str, Any]:
    schema = model.model_json_schema(by_alias=False)
    description = tool_description(name)
    if description is None:
        return inline_input_schema(schema)
    describe_fields(schema, model.__name__)
    definitions: dict[str, Any] = schema.get("$defs", {})
    for model_name, definition in definitions.items():
        describe_fields(definition, model_name)
    examples = description_examples(description)
    for example in examples:
        model.model_validate(example)
    schema["examples"] = examples
    return inline_input_schema(schema)
