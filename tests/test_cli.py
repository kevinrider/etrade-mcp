import asyncio
import json
import os
import sys
from typing import Any

import pytest
from etrade_python import ETradeSettings
from mcp import Client
from mcp.client.stdio import StdioServerParameters
from typer.testing import CliRunner

from etrade_mcp import __version__
from etrade_mcp.cli import app
from etrade_mcp.server import AdapterServer
from tests.helpers import READ_TOOLS, authenticated_http, http_server

runner = CliRunner()


def credentials(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ETRADE_CONSUMER_KEY", "fake-key")
    monkeypatch.setenv("ETRADE_CONSUMER_SECRET", "never-echo-broker-secret")


def test_version_and_help_without_credentials() -> None:
    result = runner.invoke(app, ["--version"])
    assert result.exit_code == 0 and result.stdout.strip() == __version__
    assert runner.invoke(app, ["serve", "--help"]).exit_code == 0


@pytest.mark.parametrize(
    "arguments,with_credentials",
    [
        (["serve", "--transport", "stdio"], False),
        (["serve"], True),
        (["serve", "--transport", "bad"], True),
        (["serve", "--transport", "stdio", "--host", "127.0.0.1"], True),
        (["serve", "--transport", "stdio", "--environment", "bad"], True),
        (["serve", "--transport", "stdio", "--tool-allowlist", "missing"], True),
    ],
)
def test_invalid_startup_is_sanitized(
    monkeypatch: pytest.MonkeyPatch, arguments: list[str], with_credentials: bool
) -> None:
    if with_credentials:
        credentials(monkeypatch)
    result = runner.invoke(app, arguments)
    assert result.exit_code == 2
    assert "never-echo-broker-secret" not in result.output
    assert "Traceback" not in result.output


def test_cli_transport_and_environment_precedence(monkeypatch: pytest.MonkeyPatch) -> None:
    credentials(monkeypatch)
    monkeypatch.setenv("ETRADE_MCP_TRANSPORT", "streamable-http")
    calls: list[object] = []

    def run(self: AdapterServer, **options: Any) -> None:
        calls.append(options)

    monkeypatch.setattr(AdapterServer, "run", run)
    result = runner.invoke(app, ["serve", "--transport", "stdio", "--environment", "production"])
    assert result.exit_code == 0
    assert calls == [{"transport": "stdio"}]


@pytest.mark.parametrize("failure", [False, True])
def test_cli_http_and_safe_runtime_failure(monkeypatch: pytest.MonkeyPatch, failure: bool) -> None:
    credentials(monkeypatch)
    monkeypatch.setenv("ETRADE_MCP_HTTP_BEARER_TOKEN", "never-echo-http-secret")
    calls: list[dict[str, Any]] = []

    def run(*args: Any, **options: Any) -> None:
        calls.append(options)
        if failure:
            raise RuntimeError("never-echo-http-secret")

    monkeypatch.setattr("etrade_mcp.cli.uvicorn.run", run)
    result = runner.invoke(app, ["serve"])
    assert result.exit_code == (1 if failure else 0)
    assert calls[0]["host"] == "127.0.0.1"
    assert calls[0]["port"] == 8000
    assert not calls[0]["access_log"] and not calls[0]["proxy_headers"]
    assert "never-echo-http-secret" not in result.output


def test_keyboard_interrupt_is_not_reported_as_internal_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    credentials(monkeypatch)

    def run(self: AdapterServer, **options: Any) -> None:
        raise KeyboardInterrupt

    monkeypatch.setattr(AdapterServer, "run", run)
    result = runner.invoke(app, ["serve", "--transport", "stdio"])
    assert result.exit_code != 0
    assert "internal failure" not in result.output


async def test_actual_stdio_cli_protocol_and_stdout() -> None:
    environment = os.environ.copy()
    environment.update(
        {
            "ETRADE_CONSUMER_KEY": "fake-key",
            "ETRADE_CONSUMER_SECRET": "never-echo-broker-secret",
            "ETRADE_ENVIRONMENT": "sandbox",
        }
    )
    process = await asyncio.create_subprocess_exec(
        sys.executable,
        "-m",
        "etrade_mcp",
        "serve",
        "--transport",
        "stdio",
        env=environment,
        limit=4 * 1024 * 1024,
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
            line = await asyncio.wait_for(process.stdout.readline(), 10)
            assert line, "Server exited before replying"
            decoded = json.loads(line)
            if decoded.get("id") == message.get("id"):
                return decoded

    try:
        initialized = await request(
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
        assert initialized["result"]["serverInfo"]["version"] == __version__
        process.stdin.write(b'{"jsonrpc":"2.0","method":"notifications/initialized"}\n')
        await process.stdin.drain()
        discovery = await request({"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
        assert {tool["name"] for tool in discovery["result"]["tools"]} == READ_TOOLS
        result = await request(
            {
                "jsonrpc": "2.0",
                "id": 3,
                "method": "tools/call",
                "params": {"name": "server_status", "arguments": {}},
            }
        )
        encoded = json.dumps(result)
        assert result["result"]["structuredContent"]["data"]["credential_status"] == "missing"
        assert "never-echo" not in encoded
        process.stdin.close()
        assert await asyncio.wait_for(process.wait(), 10) == 0
        assert process.stderr is not None
        assert b"never-echo" not in await process.stderr.read()
    finally:
        if process.returncode is None:
            process.kill()
            await process.wait()


@pytest.mark.parametrize("allowlist", [None, "", "server_status"])
async def test_stdio_http_schema_and_allowlist_parity(
    broker: ETradeSettings, allowlist: str | None
) -> None:
    environment = os.environ.copy()
    environment.update(ETRADE_CONSUMER_KEY="fake-key", ETRADE_CONSUMER_SECRET="fake-secret")
    args = ["-m", "etrade_mcp", "serve", "--transport", "stdio"]
    if allowlist is not None:
        args.extend(["--tool-allowlist", allowlist])
    async with Client(
        StdioServerParameters(command=sys.executable, args=args, env=environment)
    ) as stdio:
        async with http_server(broker, tool_allowlist=allowlist) as (url, _):
            async with Client(authenticated_http(url)) as http:
                assert (await stdio.list_tools()).tools == (await http.list_tools()).tools
                for client in (stdio, http):
                    result = await client.call_tool("server_status")
                    assert bool(result.is_error) == (allowlist == "")
                    hidden = await client.call_tool("orders_place")
                    assert hidden.is_error
