"""Final offline audit of protocol scope, pagination, and transport/process loss."""

import asyncio
import json
import os
import sys
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from copy import deepcopy
from pathlib import Path
from typing import Any, Literal
from urllib.parse import urlsplit

import httpx
import pytest
from etrade_python import ETradeSettings
from mcp import Client
from mcp.client.stdio import StdioServerParameters

from tests.audit_cases import page_response, wait_until
from tests.helpers import ALL_TOOLS, DEFAULT_TOOLS, TOKEN, authenticated_http, http_server
from tests.mutation_cases import MUTATIONS, MutationCase, response
from tests.read_cases import CASES
from tests.test_reads import broker_factory
from tests.test_server import payload


def records(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    try:
        return [json.loads(line) for line in path.read_text().splitlines()]
    except json.JSONDecodeError:
        return []  # The worker may be between creating and flushing a record.


def parameters(record: Path, scenario: str, **settings: str) -> StdioServerParameters:
    return StdioServerParameters(
        command=sys.executable,
        args=["-m", "tests.audit_worker", "--record-path", str(record), "--scenario", scenario],
        env={**os.environ, "ETRADE_MCP_TRANSPORT": "stdio", **settings},
    )


@pytest.mark.parametrize("mode", ["auto", "legacy"])
async def test_all_read_fields_over_actual_stdio(
    mode: Literal["auto", "legacy"], tmp_path: Path
) -> None:
    record = tmp_path / "reads.jsonl"
    async with Client(parameters(record, "reads"), mode=mode) as client:
        for case in CASES:
            result = await client.call_tool(case.tool, case.arguments)
            assert not result.is_error, result.model_dump_json()
            assert payload(result)["data"] is not None
            await client.session.validate_tool_result(case.tool, result)
    assert records(record) == [
        {"method": "GET", "path": case.path, "params": case.params, "body": None} for case in CASES
    ]


SCOPES: list[tuple[str | None, bool, bool, set[str]]] = [
    (None, False, False, DEFAULT_TOOLS),
    ("", True, True, set()),
    ("market_get_quote", False, False, {"market_get_quote"}),
    (
        "server_status,orders_preview_equity,orders_preview_change_equity,orders_place,alerts_delete",
        True,
        False,
        {"server_status", "orders_preview_equity", "orders_preview_change_equity", "orders_place"},
    ),
    (None, True, True, ALL_TOOLS),
]


@pytest.mark.parametrize("wire", ["http", "stdio"])
@pytest.mark.parametrize("allowlist,orders,alerts,expected", SCOPES)
async def test_scoped_catalogs_and_hidden_tools_over_both_transports(
    broker: ETradeSettings,
    tmp_path: Path,
    wire: str,
    allowlist: str | None,
    orders: bool,
    alerts: bool,
    expected: set[str],
) -> None:
    calls: list[httpx.Request] = []

    def forbidden(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        raise AssertionError("Hidden/invalid calls must not dispatch")

    async def check(client: Client) -> None:
        tools = {tool.name: tool for tool in (await client.list_tools()).tools}
        assert tools.keys() == expected
        for name in (
            "accounts_list",
            "orders_preview_equity",
            "orders_place",
            "alerts_delete",
            "results_read",
            "orders_prepare",
            "_private",
        ):
            result = await client.call_tool(name, {"untrusted": "private-sentinel"})
            assert result.is_error
            assert "private-sentinel" not in result.model_dump_json()
            error = payload(result)["error"]["code"]
            denied_by_allowlist = allowlist is not None and name not in allowlist.split(",")
            disabled = (name == "orders_place" and not orders) or (
                name == "alerts_delete" and not alerts
            )
            if name in expected:
                expected_error = "invalid_input"
            elif disabled and not denied_by_allowlist:
                expected_error = "execution_disabled"
            else:
                expected_error = "tool_not_available"
            assert error == expected_error
        if "market_get_quote" in tools:
            invalid = await client.call_tool("market_get_quote", {"symbol": ""})
            assert invalid.is_error

    if wire == "http":
        async with http_server(
            broker,
            client_factory=broker_factory(forbidden),
            tool_allowlist=allowlist,
            enable_order_execution=orders,
            enable_alert_deletion=alerts,
        ) as (url, _):
            async with Client(authenticated_http(url)) as client:
                await check(client)
        assert calls == []
    else:
        record = tmp_path / "scope.jsonl"
        settings = {
            "ETRADE_MCP_ENABLE_ORDER_EXECUTION": str(orders),
            "ETRADE_MCP_ENABLE_ALERT_DELETION": str(alerts),
        }
        if allowlist is not None:
            settings["ETRADE_MCP_TOOL_ALLOWLIST"] = allowlist
        async with Client(parameters(record, "reads", **settings)) as client:
            await check(client)
        assert records(record) == []


@pytest.mark.parametrize("wire", ["http", "stdio"])
async def test_explicit_pagination_to_terminal_empty_pages(
    broker: ETradeSettings, tmp_path: Path, wire: str
) -> None:
    seen: list[dict[str, Any]] = []
    record = tmp_path / "pages.jsonl"

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append({"path": request.url.path, "params": dict(request.url.params)})
        return page_response(request)

    def observed() -> list[dict[str, Any]]:
        return seen if wire == "http" else records(record)

    async def check(client: Client) -> None:
        for tool in ("transactions_list", "orders_list", "portfolio_get_positions"):
            before = len(observed())
            request: dict[str, Any] = {"count": 1}
            if tool == "portfolio_get_positions":
                request["page_number"] = 1
            args = {"account_id_key": "synthetic-key", "request": request}
            first = await client.call_tool(tool, args)
            assert not first.is_error, first.model_dump_json()
            data = payload(first)["data"]
            assert len(observed()) == before + 1
            if tool == "transactions_list":
                assert [item["transactionId"] for item in data["transaction"]] == ["boundary"]
                assert data["moreTransactions"] is True
                request["marker"] = data["marker"]
            elif tool == "orders_list":
                assert [item["orderId"] for item in data["order"]] == [17]
                request["marker"] = data["marker"]
            else:
                page = data["accountPortfolio"][0]
                assert [item["positionId"] for item in page["position"]] == [1]
                request["page_number"] = int(page["nextPageNo"])
            last = await client.call_tool(tool, args)
            assert not last.is_error, last.model_dump_json()
            data = payload(last)["data"]
            assert len(observed()) == before + 2
            if tool == "transactions_list":
                assert data["transaction"] == [] and data["moreTransactions"] is False
                assert data["marker"] == ""
            elif tool == "orders_list":
                assert data["order"] == [] and data["marker"] == ""
            else:
                assert data["accountPortfolio"][0]["position"] == []
                assert data["accountPortfolio"][0]["nextPageNo"] == ""
            await client.session.validate_tool_result(tool, last)
        assert [item["params"] for item in observed()] == [
            {"count": "1", "sortOrder": "DESC"},
            {"count": "1", "sortOrder": "DESC", "marker": "next-transaction"},
            {"count": "1"},
            {"count": "1", "marker": "next-order"},
            {"count": "1", "pageNumber": "1"},
            {"count": "1", "pageNumber": "2"},
        ]

    if wire == "http":
        async with http_server(broker, client_factory=broker_factory(handler)) as (url, _):
            async with Client(authenticated_http(url)) as client:
                await check(client)
    else:
        async with Client(parameters(record, "pages")) as client:
            await check(client)


@asynccontextmanager
async def raw_worker(
    record: Path, release: Path, stderr: Path
) -> AsyncGenerator[asyncio.subprocess.Process]:
    params = parameters(
        record,
        "lifecycle",
        ETRADE_MCP_ENABLE_ORDER_EXECUTION="true",
        ETRADE_MCP_ENABLE_ALERT_DELETION="true",
        ETRADE_MCP_DEBUG_TOOL_CALLS="true",
    )
    with stderr.open("wb") as errlog:
        process = await asyncio.create_subprocess_exec(
            params.command,
            *params.args,
            "--release-path",
            str(release),
            env=params.env,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=errlog,
            limit=4 * 1024 * 1024,
        )
        try:
            yield process
        finally:
            if process.returncode is None:
                process.kill()
            await asyncio.wait_for(process.wait(), 10)


async def send(process: asyncio.subprocess.Process, message: dict[str, Any]) -> None:
    assert process.stdin is not None
    process.stdin.write(json.dumps(message).encode() + b"\n")
    await process.stdin.drain()


async def reply(process: asyncio.subprocess.Process, request_id: int) -> dict[str, Any]:
    assert process.stdout is not None
    async with asyncio.timeout(10):
        while True:
            line = await process.stdout.readline()
            assert line, "Server exited without replying"
            value = json.loads(line)
            if value.get("id") == request_id:
                return value


async def initialize(process: asyncio.subprocess.Process) -> None:
    await send(
        process,
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": "2025-11-25",
                "capabilities": {},
                "clientInfo": {"name": "offline-audit", "version": "1"},
            },
        },
    )
    assert "result" in await reply(process, 1)
    await send(process, {"jsonrpc": "2.0", "method": "notifications/initialized"})


@pytest.mark.parametrize("case", MUTATIONS, ids=lambda case: case.tool)
async def test_process_death_after_dispatch_and_restart_never_replays(
    tmp_path: Path, case: MutationCase
) -> None:
    record, release = tmp_path / "attempts.jsonl", tmp_path / "release"
    first_err, second_err = tmp_path / "first.stderr", tmp_path / "second.stderr"
    async with raw_worker(record, release, first_err) as process:
        await initialize(process)
        await send(
            process,
            {
                "jsonrpc": "2.0",
                "id": 2,
                "method": "tools/call",
                "params": {"name": case.tool, "arguments": case.arguments},
            },
        )
        await asyncio.to_thread(wait_until, lambda: len(records(record)) == 1)
        assert records(record)[0]["body"] == case.body
        process.kill()
        await asyncio.wait_for(process.wait(), 10)
    async with raw_worker(record, release, second_err) as restarted:
        await initialize(restarted)
        await send(
            restarted,
            {
                "jsonrpc": "2.0",
                "id": 3,
                "method": "tools/call",
                "params": {"name": "server_status", "arguments": {}},
            },
        )
        assert not (await reply(restarted, 3))["result"]["isError"]
        assert len(records(record)) == 1
        release.touch()
        recovery_tool = "alerts_list" if case.tool == "alerts_delete" else "orders_list"
        recovery_args = {} if case.tool == "alerts_delete" else {"account_id_key": "synthetic-key"}
        await send(
            restarted,
            {
                "jsonrpc": "2.0",
                "id": 4,
                "method": "tools/call",
                "params": {"name": recovery_tool, "arguments": recovery_args},
            },
        )
        recovery = (await reply(restarted, 4))["result"]
        assert not recovery["isError"]
        if case.tool == "alerts_delete":
            assert recovery["structuredContent"]["data"]["totalAlerts"] == 0
        else:
            assert recovery["structuredContent"]["data"]["order"][0]["orderId"] == 701
        await send(
            restarted,
            {
                "jsonrpc": "2.0",
                "id": 5,
                "method": "tools/call",
                "params": {"name": case.tool, "arguments": case.arguments},
            },
        )
        assert not (await reply(restarted, 5))["result"]["isError"]
        assert restarted.stdin is not None
        restarted.stdin.close()
        assert await asyncio.wait_for(restarted.wait(), 10) == 0
    attempts = [item for item in records(record) if item.get("method") not in {None, "GET"}]
    assert len(attempts) == 2
    assert attempts[0] == attempts[1]  # An explicit repeat is a new, unchanged attempt.
    assert await asyncio.to_thread(lambda: {path.name for path in tmp_path.iterdir()}) == {
        "attempts.jsonl",
        "release",
        "first.stderr",
        "second.stderr",
    }  # No server execution journal or credential files are created in the isolated directory.
    for errlog in (first_err, second_err):
        text = errlog.read_text()
        for private in ("synthetic-key", "fake-broker-secret", "fake-private-account-response"):
            assert private not in text


@pytest.mark.parametrize("case", MUTATIONS, ids=lambda case: case.tool)
async def test_http_socket_loss_after_dispatch_never_redispatches(
    broker: ETradeSettings, case: MutationCase
) -> None:
    started, release, finished = asyncio.Event(), asyncio.Event(), asyncio.Event()
    seen: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        started.set()
        await release.wait()
        finished.set()
        return response(request)

    async with http_server(
        broker,
        client_factory=broker_factory(handler),
        enable_order_execution=True,
        enable_alert_deletion=True,
    ) as (url, _):
        address = urlsplit(url)
        assert address.hostname is not None and address.port is not None
        _, writer = await asyncio.open_connection(address.hostname, address.port)
        body = json.dumps(
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "tools/call",
                "params": {
                    "name": case.tool,
                    "arguments": deepcopy(case.arguments),
                    "_meta": {"io.modelcontextprotocol/protocolVersion": "2025-11-25"},
                },
            }
        ).encode()
        writer.write(
            (
                f"POST /mcp HTTP/1.1\r\nHost: {address.netloc}\r\n"
                f"Authorization: Bearer {TOKEN}\r\n"
                "Accept: application/json, text/event-stream\r\nContent-Type: application/json\r\n"
                f"MCP-Protocol-Version: 2025-11-25\r\nContent-Length: {len(body)}\r\n\r\n"
            ).encode()
            + body
        )
        try:
            await writer.drain()
            await asyncio.wait_for(started.wait(), 10)
            writer.close()
            await writer.wait_closed()
            release.set()
            await asyncio.wait_for(finished.wait(), 10)
            async with Client(authenticated_http(url)) as client:
                assert not (await client.call_tool("server_status")).is_error
                assert len(seen) == 1
        finally:
            release.set()
            writer.close()
            await writer.wait_closed()
    assert len(seen) == 1
    assert seen[0].method == case.method
    assert seen[0].url.path == case.path
    assert (json.loads(seen[0].content) if seen[0].content else None) == case.body
