import os
import sys
from typing import Any, Literal

import pytest
from etrade_python import ETradeSettings
from mcp import Client
from mcp.client.stdio import StdioServerParameters
from mcp.types import CallToolResult

from tests.helpers import READ_TOOLS, authenticated_http, http_server
from tests.read_cases import CASES
from tests.response_contract_worker import client_factory, tool_specs
from tests.test_server import payload


@pytest.mark.parametrize("mode", ["auto", "legacy"])
@pytest.mark.parametrize("wire", ["http", "stdio"])
async def test_native_tool_status_and_output_schema_contract(
    broker: ETradeSettings, mode: Literal["auto", "legacy"], wire: str
) -> None:
    async def check(client: Client) -> None:
        tools = (await client.list_tools()).tools
        assert {tool.name for tool in tools} == READ_TOOLS
        for tool in tools:
            assert tool.output_schema is not None
            assert set(tool.output_schema["properties"]) == {"data", "error", "meta"}
            assert "ok" not in tool.output_schema.get("required", [])

        async def verify(name: str, result: CallToolResult, code: str | None = None) -> None:
            data = payload(result)  # Also verifies text equality and the exact envelope fields.
            assert result.is_error is (code is not None)
            assert data["meta"]["environment"] == "sandbox"
            assert data["meta"]["profile"] == "default"
            if code is None:
                assert data["data"] is not None and data["error"] is None
            else:
                assert data["data"] is None and data["error"]["code"] == code
                assert "fake-private" not in result.model_dump_json()
            # The SDK normally skips schema validation for isError results;
            # invoke its public validator explicitly for both outcomes.
            await client.session.validate_tool_result(name, result)

        status = await client.call_tool("server_status")
        await verify("server_status", status)
        for case in CASES:
            await verify(case.tool, await client.call_tool(case.tool, case.arguments))

        failures: list[tuple[str, dict[str, Any], str]] = [
            ("server_status", {"unknown": "fake-private-input"}, "invalid_input"),
            ("market_get_quote", {"symbol": " "}, "invalid_input"),
            ("market_get_quote", {"symbol": "REJECT"}, "broker_rejection"),
            ("market_get_quote", {"symbol": "BROKEN"}, "invalid_broker_response"),
            ("mutation_probe", {}, "execution_disabled"),
            ("unknown_tool", {}, "tool_not_available"),
        ]
        for name, arguments, code in failures:
            result = await client.call_tool(name, arguments)
            # Hidden tools have no discovery schema. Their error envelope is
            # shared with every advertised tool, including server_status.
            schema_name = name if name in READ_TOOLS else "server_status"
            await verify(schema_name, result, code)

        # Prove discovery schemas reject the removed field rather than merely
        # making it optional, including on an otherwise valid success payload.
        with pytest.raises(RuntimeError, match="Invalid structured content"):
            await client.session.validate_tool_result(
                "server_status",
                status.model_copy(update={"structured_content": {**payload(status), "ok": True}}),
            )

    if wire == "http":
        async with http_server(broker, client_factory=client_factory, tools=tool_specs()) as (
            url,
            _,
        ):
            async with Client(authenticated_http(url), mode=mode) as client:
                await check(client)
    else:
        async with Client(
            StdioServerParameters(
                command=sys.executable,
                args=["-m", "tests.response_contract_worker"],
                env=os.environ.copy(),
            ),
            mode=mode,
        ) as client:
            await check(client)
