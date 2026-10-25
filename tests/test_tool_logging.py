"""Request diagnostics are opt-in, redacted, bounded, and protocol-independent."""

import asyncio
import io
import json
import logging
import os
import sys
from collections.abc import AsyncGenerator, Generator
from contextlib import asynccontextmanager
from copy import deepcopy
from pathlib import Path
from typing import Any, Literal
from urllib.parse import quote

import httpx
import pytest
from etrade_python import ETradeSettings
from mcp import Client
from mcp.client.stdio import StdioServerParameters, stdio_client
from mcp.types import CallToolResult, TextContent
from pydantic import BaseModel
from typer.testing import CliRunner

from etrade_mcp.cli import app
from etrade_mcp.config import ServerConfig, ServerSettings
from etrade_mcp.order_families import OrdersPreviewEquityInput
from etrade_mcp.server import EmptyInput
from etrade_mcp.tool_logging import (
    LOGGER,
    MAX_DEPTH,
    MAX_EVENT_BYTES,
    MAX_JSON_STRING,
    REDACTED,
    ArgumentPreview,
    ToolTrace,
    configure_tool_logging,
)
from etrade_mcp.tools.orders import OrdersPreviewInput
from etrade_mcp.validation import Node
from tests.helpers import TOKEN, authenticated_http, http_server
from tests.preview_cases import REQUESTS
from tests.test_reads import broker_factory
from tests.test_server import payload
from tests.tool_logging_worker import RESPONSE_ONLY, logging_tools, response
from tests.validation_cases import equity

PRIVATE = "private-account-identity"


@pytest.fixture(autouse=True)
def reset_trace_logger() -> Generator[None]:
    yield
    configure_tool_logging(False)


def events(text: str) -> list[dict[str, Any]]:
    return [json.loads(line) for line in text.splitlines() if line.startswith('{"event":')]


def preview(value: Any, model: type[BaseModel] = OrdersPreviewEquityInput) -> dict[str, Any]:
    return ArgumentPreview((TOKEN, "fake-broker-secret")).render(value, [Node(model)])


def test_preview_preserves_types_and_masks_identifiers() -> None:
    arguments = equity(price_type="LIMIT", limit_price="300.50")
    arguments["account_id_key"] = PRIVATE
    arguments["request"]["client_order_id"] = PRIVATE
    before = deepcopy(arguments)
    value = preview(arguments)
    assert arguments == before
    assert value["fields"]["account_id_key"]["value"] == REDACTED
    request = value["fields"]["request"]
    assert request["type"] == "object"
    assert request["fields"]["symbol"]["value"] == "SYN"
    assert request["fields"]["limit_price"]["value"] == "300.50"
    assert request["fields"]["quantity"]["type"] == "string"
    assert request["fields"]["client_order_id"]["value"] == REDACTED
    arguments["request"] = json.dumps(arguments["request"])
    value = preview(arguments)["fields"]["request"]
    assert value["type"] == "string" and value["decoded_preview"]["type"] == "object"
    assert value["decoded_preview"]["fields"]["limit_price"]["value"] == "300.50"
    assert PRIVATE not in json.dumps(value)
    assert isinstance(arguments["request"], str)


def test_unknown_fields_malformed_strings_and_secrets_are_withheld() -> None:
    arguments = equity(symbol=TOKEN, price_type=quote("fake-broker-secret", safe=""))
    arguments[PRIVATE] = {"authorization": TOKEN}
    arguments["request"][PRIVATE] = "private-customer-value"
    value = preview(arguments)
    text = json.dumps(value)
    for secret in (PRIVATE, TOKEN, "fake-broker-secret", "private-customer-value", "authorization"):
        assert secret not in text
    assert value["omitted_fields"] == 1
    assert value["fields"]["request"]["omitted_fields"] == 1
    arguments["request"] = '{"password":"private-customer-value"'
    value = preview(arguments)["fields"]["request"]
    assert value["unparseable_json"] and "private-customer-value" not in str(value)
    arguments["request"] = "Z" * (MAX_JSON_STRING + 1)
    assert preview(arguments)["fields"]["request"]["truncated"]
    arguments["account_id_key"] = {"symbol": PRIVATE}
    assert preview(arguments)["fields"]["account_id_key"]["value"] == REDACTED


def test_aliases_arrays_and_preview_budgets() -> None:
    from etrade_python import PreviewOrderRequest

    arguments: dict[str, Any] = {
        "account_id_key": PRIVATE,
        "request": PreviewOrderRequest.model_validate(REQUESTS["equity"]).request_body()[
            "PreviewOrderRequest"
        ],
    }
    value = preview(arguments, OrdersPreviewInput)
    detail = value["fields"]["request"]["fields"]["Order"]["items"][0]
    assert detail["fields"]["Instrument"]["items"][0]["fields"]["quantity"]["value"] == "100"
    arguments["request"]["Order"] *= 20
    assert preview(arguments, OrdersPreviewInput)["fields"]["request"]["fields"]["Order"][
        "truncated"
    ]
    budget = ArgumentPreview(())
    budget.remaining = 0
    assert budget.render({}, [Node(EmptyInput)])["truncated"]
    assert ArgumentPreview(()).render({}, [Node(EmptyInput)], depth=MAX_DEPTH)["truncated"]
    assert (
        ArgumentPreview(()).render("{}", [Node(EmptyInput)])["decoded_preview"]["type"] == "object"
    )
    assert preview({"request": '{"quantity":NaN}'})["fields"]["request"]["unparseable_json"]


def test_scalar_whitelist_and_log_size(
    config: ServerConfig, capsys: pytest.CaptureFixture[str]
) -> None:
    renderer = ArgumentPreview(("12", TOKEN))
    assert renderer.scalar(12, "quantity") == REDACTED
    assert renderer.scalar(1 << 300, "quantity") == REDACTED
    assert renderer.scalar(float("inf"), "quantity") == REDACTED
    assert renderer.scalar(123, "order_id") == REDACTED
    assert renderer.scalar("Some private name", "search") == REDACTED
    assert renderer.scalar("user@example.com", "symbol") == REDACTED
    assert renderer.scalar(True, "include_weekly") is True
    assert renderer.scalar(None, "quantity") is None
    assert renderer.scalar(object(), "quantity") == REDACTED
    configure_tool_logging(True)
    configured = config.model_copy(
        update={"server": config.server.model_copy(update={"debug_tool_calls": True})}
    )
    trace = ToolTrace(configured, "orders_preview_equity", OrdersPreviewEquityInput)
    trace.emit("tool_call.received", arguments="Z" * (MAX_EVENT_BYTES + 1))
    captured = capsys.readouterr()
    assert captured.out == ""
    assert len(captured.err.encode()) <= MAX_EVENT_BYTES
    assert events(captured.err)[0]["truncated"]


@pytest.mark.parametrize("enabled", [False, True])
@pytest.mark.parametrize("wire", ["http", "stdio"])
@pytest.mark.parametrize("mode", ["auto", "legacy"])
async def test_logging_over_actual_protocol(
    broker: ETradeSettings,
    enabled: bool,
    wire: str,
    mode: Literal["auto", "legacy"],
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    configure_tool_logging(enabled)
    sent: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        sent.append(request)
        return response(request)

    async def check(client: Client) -> None:
        calls = [equity(), equity(), equity(), equity()]
        calls[0]["account_id_key"] = PRIVATE
        calls[1]["request"] = json.dumps(calls[1]["request"])
        calls[2]["request"] = {PRIVATE: TOKEN}
        calls[3]["account_id_key"] = "reject-account"
        for index, arguments in enumerate(calls):
            before = deepcopy(arguments)
            result = await client.call_tool("orders_preview_equity", arguments)
            assert result.is_error == (index != 0)
            if index == 0:
                assert payload(result)["data"]["broker_preview"]["accountId"] == "synthetic-account"
            if index == 1:
                assert payload(result)["error"]["validation_errors"][0]["code"] == "model_type"
            if index == 3:
                assert payload(result)["error"]["broker_message"] == RESPONSE_ONLY
            await client.session.validate_tool_result("orders_preview_equity", result)
            assert arguments == before

    if wire == "http":
        async with http_server(
            broker,
            tools=logging_tools(),
            client_factory=broker_factory(handler),
            debug_tool_calls=enabled,
        ) as (url, _):
            async with Client(authenticated_http(url), mode=mode) as client:
                await check(client)
        assert len(sent) == 2
        captured = capsys.readouterr()
        assert captured.out == ""
        stderr = captured.err
    else:
        stderr_path = tmp_path / "worker.stderr"
        with stderr_path.open("w+") as stderr_file:

            @asynccontextmanager
            async def connection() -> AsyncGenerator[tuple[Any, Any]]:
                async with stdio_client(
                    StdioServerParameters(
                        command=sys.executable,
                        args=["-m", "tests.tool_logging_worker"],
                        env={**os.environ, "ETRADE_MCP_DEBUG_TOOL_CALLS": str(enabled).lower()},
                    ),
                    errlog=stderr_file,
                ) as streams:
                    yield streams

            async with Client(connection(), mode=mode) as client:
                await check(client)
        stderr = stderr_path.read_text()
    records = events(stderr)
    if not enabled:
        assert records == []
        return
    assert len(records) == 8
    ids = {record["call_id"] for record in records}
    assert len(ids) == 4 and all(
        sum(r["call_id"] == call_id for r in records) == 2 for call_id in ids
    )
    received = [r for r in records if r["event"] == "tool_call.received"]
    assert received[0]["arguments"]["fields"]["request"]["type"] == "object"
    assert received[1]["arguments"]["fields"]["request"]["type"] == "string"
    completed = [r for r in records if r["event"] == "tool_call.completed"]
    assert [r["outcome"] for r in completed] == ["success", "error", "error", "error"]
    assert completed[1]["validation_errors"][0]["code"] == "model_type"
    assert completed[3]["error_code"] == "broker_rejection"
    for secret in (PRIVATE, TOKEN, "synthetic-account", RESPONSE_ONLY, "Synthetic preview warning"):
        assert secret not in stderr


async def test_formatting_and_sink_failures_do_not_change_results(
    broker: ETradeSettings,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    configure_tool_logging(True)

    def broken(*args: Any, **kwargs: Any) -> Any:
        raise RuntimeError(PRIVATE)

    async with http_server(
        broker,
        tools=logging_tools(),
        client_factory=broker_factory(response),
        debug_tool_calls=True,
    ) as (url, _):
        async with Client(authenticated_http(url)) as client:
            with monkeypatch.context() as patch:
                patch.setattr(ArgumentPreview, "render", broken)
                assert not (await client.call_tool("orders_preview_equity", equity())).is_error
            with monkeypatch.context() as patch:
                patch.setattr(LOGGER, "info", broken)
                assert not (await client.call_tool("orders_preview_equity", equity())).is_error

            class BrokenStream(io.StringIO):
                def write(self, text: str) -> int:
                    raise OSError(PRIVATE)

            with monkeypatch.context() as patch:
                patch.setattr(sys, "stderr", BrokenStream())
                configure_tool_logging(True)
                assert not (await client.call_tool("orders_preview_equity", equity())).is_error


async def test_concurrent_calls_have_distinct_ids(
    broker: ETradeSettings,
    capsys: pytest.CaptureFixture[str],
) -> None:
    configure_tool_logging(True)
    async with http_server(
        broker,
        tools=logging_tools(),
        client_factory=broker_factory(response),
        debug_tool_calls=True,
    ) as (url, _):
        async with Client(authenticated_http(url)) as client:
            results = await asyncio.gather(
                *[client.call_tool("orders_preview_equity", equity()) for _ in range(8)]
            )
            assert all(not result.is_error for result in results)
    records = events(capsys.readouterr().err)
    assert len(records) == 16 and len({record["call_id"] for record in records}) == 8


def test_completion_never_logs_response_text(
    config: ServerConfig, capsys: pytest.CaptureFixture[str]
) -> None:
    configure_tool_logging(True)
    configured = config.model_copy(
        update={"server": config.server.model_copy(update={"debug_tool_calls": True})}
    )
    trace = ToolTrace(configured, "orders_preview_equity", OrdersPreviewEquityInput)
    trace.finished(
        CallToolResult(
            content=[TextContent(type="text", text=PRIVATE)],
            is_error=True,
            structured_content={
                "error": {
                    "code": "broker_rejection",
                    "message": PRIVATE,
                    "validation_errors": [{"path": [PRIVATE], "code": PRIVATE}],
                }
            },
        )
    )
    text = capsys.readouterr().err
    assert PRIVATE not in text
    assert events(text)[0]["validation_errors"] == [{"path": [], "code": "invalid_value"}]


def test_flag_environment_and_cli_override(monkeypatch: pytest.MonkeyPatch) -> None:
    assert not ServerSettings(transport="stdio").debug_tool_calls
    monkeypatch.setenv("ETRADE_MCP_DEBUG_TOOL_CALLS", "true")
    assert ServerSettings(transport="stdio").debug_tool_calls
    assert not ServerSettings(transport="stdio", debug_tool_calls=False).debug_tool_calls
    monkeypatch.setenv("ETRADE_CONSUMER_KEY", "fake-key")
    monkeypatch.setenv("ETRADE_CONSUMER_SECRET", "fake-broker-secret")
    observed: list[bool] = []

    class Server:
        def run(self, **kwargs: Any) -> None:
            observed.append(LOGGER.level == logging.INFO)

    def factory(config: ServerConfig) -> Server:
        return Server()

    monkeypatch.setattr("etrade_mcp.cli.create_server", factory)
    runner = CliRunner()
    assert runner.invoke(app, ["serve", "--transport", "stdio"]).exit_code == 0
    assert (
        runner.invoke(app, ["serve", "--transport", "stdio", "--no-debug-tool-calls"]).exit_code
        == 0
    )
    assert observed == [True, False]


@pytest.mark.parametrize("selection", ["default", "flag", "environment", "override"])
async def test_actual_cli_keeps_stdout_protocol_only(selection: str) -> None:
    environment = {
        **os.environ,
        "ETRADE_CONSUMER_KEY": "fake-key",
        "ETRADE_CONSUMER_SECRET": "never-echo-broker-secret",
        "ETRADE_ENVIRONMENT": "sandbox",
    }
    args = [
        "-m",
        "etrade_mcp",
        "serve",
        "--transport",
        "stdio",
        "--tool-allowlist",
        "server_status,orders_preview_equity",
    ]
    if selection in {"environment", "override"}:
        environment["ETRADE_MCP_DEBUG_TOOL_CALLS"] = "true"
    if selection == "flag":
        args.append("--debug-tool-calls")
    elif selection == "override":
        args.append("--no-debug-tool-calls")
    process = await asyncio.create_subprocess_exec(
        sys.executable,
        *args,
        env=environment,
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    assert process.stdin is not None and process.stdout is not None

    async def request(message: dict[str, Any]) -> dict[str, Any]:
        assert process.stdin is not None and process.stdout is not None
        process.stdin.write(json.dumps(message).encode() + b"\n")
        await process.stdin.drain()
        while True:
            line = await asyncio.wait_for(process.stdout.readline(), 15)
            assert line, "Server exited before replying"
            decoded = json.loads(line)
            assert decoded["jsonrpc"] == "2.0"
            if decoded.get("id") == message.get("id"):
                return decoded

    try:
        await request(
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {
                    "protocolVersion": "2025-11-25",
                    "capabilities": {},
                    "clientInfo": {"name": "offline-test", "version": "1"},
                },
            }
        )
        process.stdin.write(b'{"jsonrpc":"2.0","method":"notifications/initialized"}\n')
        await process.stdin.drain()
        success = await request(
            {
                "jsonrpc": "2.0",
                "id": 2,
                "method": "tools/call",
                "params": {"name": "server_status", "arguments": {}},
            }
        )
        assert not success["result"].get("isError", False)
        failure = await request(
            {
                "jsonrpc": "2.0",
                "id": 3,
                "method": "tools/call",
                "params": {
                    "name": "orders_preview_equity",
                    "arguments": {
                        "account_id_key": PRIVATE,
                        "request": json.dumps(equity()["request"]),
                    },
                },
            }
        )
        assert failure["result"]["isError"]
        process.stdin.close()
        remaining, stderr_bytes = await asyncio.wait_for(process.communicate(), 15)
        assert process.returncode == 0
        for line in remaining.splitlines():
            assert json.loads(line)["jsonrpc"] == "2.0"
        stderr = stderr_bytes.decode()
        assert PRIVATE not in stderr and "never-echo-broker-secret" not in stderr
        records = events(stderr)
        if selection in {"flag", "environment"}:
            assert len(records) == 4
            assert [r["outcome"] for r in records if r["event"] == "tool_call.completed"] == [
                "success",
                "error",
            ]
        else:
            assert records == []
    finally:
        if process.returncode is None:
            process.kill()
            await process.wait()


async def test_denied_and_unknown_tools_do_not_log_untrusted_arguments(
    broker: ETradeSettings,
    capsys: pytest.CaptureFixture[str],
) -> None:
    configure_tool_logging(True)
    async with http_server(
        broker,
        tools=logging_tools(),
        client_factory=broker_factory(response),
        tool_allowlist="",
        debug_tool_calls=True,
    ) as (url, _):
        async with Client(authenticated_http(url)) as client:
            for name in ("orders_preview_equity", PRIVATE):
                result = await client.call_tool(name, {"request": {"symbol": PRIVATE}})
                assert result.is_error
    stderr = capsys.readouterr().err
    assert PRIVATE not in stderr
    records = events(stderr)
    assert len(records) == 4
    assert records[2]["tool"] == "[unknown_tool]"
    assert all(r["outcome"] == "error" for r in records if "outcome" in r)
