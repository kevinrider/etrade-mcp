"""Exercise an installed server over both transports, with no broker credentials."""

from __future__ import annotations

import asyncio
import json
import os
import socket
import sys
import tempfile
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import Any

import httpx2
from mcp import Client
from mcp.client.stdio import StdioServerParameters
from mcp.client.streamable_http import streamable_http_client
from mcp.types import CallToolResult, TextContent, Tool


async def inspect(client: Client) -> list[Tool]:
    tools = (await client.list_tools()).tools
    assert {tool.name for tool in tools} == {
        "server_status",
        "accounts_list",
        "accounts_get_balance",
        "portfolio_get_positions",
        "transactions_list",
        "transactions_get",
        "market_get_quote",
        "market_get_quotes",
        "market_lookup_product",
        "market_get_option_expirations",
        "market_get_option_chain",
        "orders_list",
        "alerts_list",
        "alerts_get",
    }
    for tool in tools:
        assert tool.output_schema is not None
        assert set(tool.output_schema["properties"]) == {"data", "error", "meta"}

    async def check_result(name: str, result: CallToolResult) -> None:
        assert result.structured_content is not None
        assert set(result.structured_content) == {"data", "error", "meta"}
        assert isinstance(result.content[0], TextContent)
        assert json.loads(result.content[0].text) == result.structured_content
        await client.session.validate_tool_result(name, result)

    result = await client.call_tool("server_status")
    assert not result.is_error
    assert result.structured_content is not None
    await check_result("server_status", result)
    data = result.structured_content["data"]
    assert isinstance(data, dict)
    assert data["credential_status"] == "missing"
    assert data["order_execution_enabled"] is False
    assert data["alert_deletion_enabled"] is False
    unauthenticated = await client.call_tool("market_get_quote", {"symbol": "AAPL"})
    assert unauthenticated.is_error
    assert unauthenticated.structured_content is not None
    assert unauthenticated.structured_content["error"]["code"] == "authentication_required"
    await check_result("market_get_quote", unauthenticated)
    invalid = await client.call_tool("server_status", {"unknown": "fake-private-input"})
    assert invalid.is_error
    assert "fake-private-input" not in invalid.model_dump_json()
    await check_result("server_status", invalid)
    return tools


async def main() -> None:
    environment = {
        name: value for name, value in os.environ.items() if not name.startswith("ETRADE_")
    }
    environment.update(
        ETRADE_CONSUMER_KEY="fake-smoke-key",
        ETRADE_CONSUMER_SECRET="fake-smoke-secret",
        ETRADE_ENVIRONMENT="sandbox",
        PYTHON_KEYRING_BACKEND="keyring.backends.null.Keyring",
    )
    with tempfile.TemporaryDirectory(prefix="etrade-mcp-smoke-") as temporary:
        environment["XDG_CACHE_HOME"] = temporary
        async with Client(
            StdioServerParameters(
                command=sys.executable,
                args=["-I", "-m", "etrade_mcp", "serve", "--transport", "stdio"],
                env=environment,
                cwd=temporary,
            )
        ) as client:
            stdio_tools = await inspect(client)

        with socket.socket() as reserved:
            reserved.bind(("127.0.0.1", 0))
            port = int(reserved.getsockname()[1])
        token = "fake-smoke-http-secret"
        environment["ETRADE_MCP_HTTP_BEARER_TOKEN"] = token
        process = await asyncio.create_subprocess_exec(
            sys.executable,
            "-I",
            "-m",
            "etrade_mcp",
            "serve",
            "--port",
            str(port),
            env=environment,
            cwd=temporary,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            async with asyncio.timeout(15):
                while True:
                    if process.returncode is not None:
                        raise RuntimeError("Installed HTTP server exited during startup")
                    try:
                        _, writer = await asyncio.open_connection("127.0.0.1", port)
                    except OSError:
                        await asyncio.sleep(0.05)
                    else:
                        writer.close()
                        await writer.wait_closed()
                        break

            @asynccontextmanager
            async def connection() -> AsyncGenerator[tuple[Any, Any]]:
                async with httpx2.AsyncClient(
                    headers={"Authorization": f"Bearer {token}"}, trust_env=False
                ) as http:
                    async with streamable_http_client(
                        f"http://127.0.0.1:{port}/mcp", http_client=http
                    ) as streams:
                        yield streams[0], streams[1]

            async with Client(connection()) as client:
                assert await inspect(client) == stdio_tools
        finally:
            if process.returncode is None:
                process.terminate()
            try:
                stdout, stderr = await asyncio.wait_for(process.communicate(), 10)
            except TimeoutError:
                process.kill()
                await process.communicate()
                raise
            assert stdout == b""
            for secret in (token, "fake-smoke-secret"):
                assert secret.encode() not in stderr
        print("Installed stdio and authenticated HTTP discovery/invocation/schema parity passed")


if __name__ == "__main__":
    asyncio.run(main())
