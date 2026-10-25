"""Discovery guidance is packaged metadata, never an alternate validation layer."""

import json
import os
import sys
from copy import deepcopy
from typing import Any, Literal, Protocol, cast

import pytest
from etrade_python import ETradeSettings, PreviewOrderRequest
from jsonschema import Draft202012Validator
from mcp import Client
from mcp.client.stdio import StdioServerParameters
from pydantic import ValidationError

from etrade_mcp.config import ServerConfig
from etrade_mcp.guidance import (
    catalog,
    describe_fields,
    described_input_schema,
    description_examples,
    tool_description,
)
from etrade_mcp.inputs import PreviewRequest
from etrade_mcp.server import EmptyInput, ToolSpec, create_server, server_status
from etrade_mcp.tools import preview_tools, read_tools
from tests.helpers import DEFAULT_TOOLS, authenticated_http, http_server
from tests.preview_cases import REQUESTS


class InstanceValidator(Protocol):
    def validate(self, instance: object) -> None: ...


def without_guidance(value: Any) -> Any:
    if isinstance(value, dict):
        value = cast(dict[str, Any], value)
        return {
            k: without_guidance(v) for k, v in value.items() if k not in {"description", "examples"}
        }
    if isinstance(value, list):
        value = cast(list[Any], value)
        return [without_guidance(v) for v in value]
    return value


def specs() -> list[ToolSpec]:
    return [ToolSpec("server_status", server_status, EmptyInput), *read_tools(), *preview_tools()]


def test_guidance_coverage_examples_and_schema_constraints() -> None:
    assert set(catalog().tools) == DEFAULT_TOOLS
    assert len(catalog().tools) == len(set(catalog().tools))
    models: set[str] = set()
    for spec in specs():
        original = spec.input_model.model_json_schema(by_alias=False)
        schema = described_input_schema(spec.name, spec.input_model)
        assert without_guidance(schema) == without_guidance(original)
        assert spec.input_model.model_json_schema(by_alias=False) == original
        description = tool_description(spec.name)
        assert description and len(description) <= 4096
        examples = description_examples(description)
        assert examples and examples == schema["examples"]
        Draft202012Validator.check_schema(schema)
        validator = cast(InstanceValidator, Draft202012Validator(schema))
        for example in examples:
            validator.validate(example)
            spec.input_model.model_validate(example)
        definitions = {spec.input_model.__name__: schema, **schema.get("$defs", {})}
        models.update(definitions)
        for name, definition in definitions.items():
            assert set(catalog().models[name]) == set(definition.get("properties", {}))
            for field in definition.get("properties", {}).values():
                assert isinstance(field["description"], str) and field["description"].strip()
    assert models == set(catalog().models)


def test_injected_tool_guidance_and_stale_references() -> None:
    assert tool_description("../../private") is None
    assert described_input_schema("injected_probe", EmptyInput) == EmptyInput.model_json_schema(
        by_alias=False
    )
    with pytest.raises(ValueError, match="Field guidance does not match"):
        describe_fields({"properties": {"stale_field": {}}}, "EmptyInput")
    with pytest.raises(ValidationError):
        description_examples("```json\n[]\n```")


@pytest.mark.parametrize("wire", ["http", "stdio"])
@pytest.mark.parametrize("mode", ["auto", "legacy"])
async def test_guidance_through_actual_discovery(
    broker: ETradeSettings, wire: str, mode: Literal["auto", "legacy"], config: ServerConfig
) -> None:
    expected = {tool.name: tool for tool in await create_server(config).list_tools()}

    async def check(client: Client) -> None:
        tools = (await client.list_tools()).tools
        assert {tool.name for tool in tools} == DEFAULT_TOOLS
        for tool in tools:
            assert tool.description == expected[tool.name].description
            assert tool.input_schema == expected[tool.name].input_schema
            for example in tool.input_schema["examples"]:
                cast(InstanceValidator, Draft202012Validator(tool.input_schema)).validate(example)
        # Tool calls retain the existing error and output contracts after enrichment.
        result = await client.call_tool("orders_preview", {"account_id_key": "synthetic-key"})
        assert result.is_error
        assert result.structured_content is not None
        assert result.structured_content["error"]["code"] == "invalid_input"
        assert "synthetic-key" not in result.model_dump_json()
        await client.session.validate_tool_result("orders_preview", result)

    if wire == "http":
        async with http_server(broker) as (url, _):
            async with Client(authenticated_http(url), mode=mode) as client:
                await check(client)
    else:
        async with Client(
            StdioServerParameters(
                command=sys.executable,
                args=["-m", "etrade_mcp", "serve", "--transport", "stdio"],
                env={
                    **os.environ,
                    "ETRADE_CONSUMER_KEY": "fake-key",
                    "ETRADE_CONSUMER_SECRET": "fake-secret",
                },
            ),
            mode=mode,
        ) as client:
            await check(client)


@pytest.mark.parametrize("field", ["disclosure", "mf_quantity"])
@pytest.mark.parametrize("variant", ["omitted", "null", "empty", "all_null", "populated"])
def test_optional_order_object_serialization_is_preserved(field: str, variant: str) -> None:
    value = deepcopy(REQUESTS["equity"])
    detail = value["orders"][0]
    target = detail if field == "disclosure" else detail["instruments"][0]
    if variant != "omitted":
        target[field] = {
            "null": None,
            "empty": {},
            "all_null": {"ao_disclosure_flag": None} if field == "disclosure" else {"cash": None},
            "populated": {"ao_disclosure_flag": False}
            if field == "disclosure"
            else {"cash": "0.00"},
        }[variant]
    actual = PreviewRequest.model_validate(value).request_body()
    assert actual == PreviewOrderRequest.model_validate(value).request_body()
    broker_detail = actual["PreviewOrderRequest"]["Order"][0]
    broker_target = broker_detail if field == "disclosure" else broker_detail["Instrument"][0]
    broker_field = "disclosure" if field == "disclosure" else "mfQuantity"
    if variant in {"omitted", "null"}:
        assert broker_field not in broker_target
    elif variant in {"empty", "all_null"}:
        assert broker_target[broker_field] == {}
    else:
        expected = {"aoDisclosureFlag": False} if field == "disclosure" else {"cash": "0.00"}
        assert broker_target[broker_field] == expected


def test_preview_guidance_examples_preserve_public_client_mapping() -> None:
    for name in ("orders_preview", "orders_preview_change"):
        description = tool_description(name)
        assert description
        for arguments in description_examples(description):
            value = arguments["request"]
            assert (
                PreviewRequest.model_validate(value).request_body()
                == PreviewOrderRequest.model_validate(value).request_body()
            )
            assert "mf_quantity" not in json.dumps(value)
