import asyncio
from typing import Any, Literal

import httpx2
import pytest
from etrade_python import ETradeSettings
from mcp import Client

from etrade_mcp.config import ConfigurationError, ServerConfig
from etrade_mcp.http import BearerGate, create_http_app
from etrade_mcp.server import create_server
from tests.helpers import READ_TOOLS, TOKEN, authenticated_http, http_server
from tests.test_server import payload


@pytest.mark.parametrize("mode", ["auto", "legacy"])
async def test_actual_http_discovery_invocation_and_concurrency(
    broker: ETradeSettings, mode: Literal["auto", "legacy"]
) -> None:
    async with http_server(broker) as (url, _):
        async with Client(authenticated_http(url), mode=mode) as client:
            tools = (await client.list_tools()).tools
            assert {t.name for t in tools} == READ_TOOLS
            results = await asyncio.gather(*(client.call_tool("server_status") for _ in range(5)))
            assert all(not result.is_error for result in results)
            assert payload(results[0])["data"]["transport"] == "streamable-http"
            invalid = await client.call_tool("server_status", {"secret": TOKEN})
            assert invalid.is_error
            assert TOKEN not in invalid.model_dump_json()


@pytest.mark.parametrize(
    "headers,expected",
    [
        ({}, 401),
        ({"Authorization": "Bearer wrong"}, 401),
        ({"Authorization": "Basic " + TOKEN}, 401),
        ({"Authorization": "Bearer " + TOKEN, "Host": "evil.example"}, 421),
        ({"Authorization": "Bearer " + TOKEN, "Origin": "https://evil.example"}, 403),
    ],
)
async def test_http_access_denied_before_tool_invocation(
    broker: ETradeSettings, headers: dict[str, str], expected: int
) -> None:
    async with http_server(broker) as (url, _):
        async with httpx2.AsyncClient(trust_env=False) as http:
            response = await http.post(
                url,
                headers={"Accept": "application/json, text/event-stream", **headers},
                json={
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "tools/call",
                    "params": {"name": "server_status"},
                },
            )
            assert response.status_code == expected
            assert TOKEN not in response.text
            if expected == 401:
                assert response.headers["WWW-Authenticate"] == "Bearer"


async def test_origin_allowlist_and_query_token_rejection(broker: ETradeSettings) -> None:
    async with http_server(broker) as (url, _):
        async with httpx2.AsyncClient(trust_env=False) as http:
            response = await http.post(url + "?access_token=" + TOKEN)
            assert response.status_code == 401
            response = await http.post(
                url,
                headers={
                    "Authorization": "Bearer " + TOKEN,
                    "Origin": url.removesuffix("/mcp"),
                    "Accept": "application/json, text/event-stream",
                },
                json={
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "initialize",
                    "params": {
                        "protocolVersion": "2025-11-25",
                        "capabilities": {},
                        "clientInfo": {"name": "test", "version": "1"},
                    },
                },
            )
            assert response.status_code == 200
            assert "access-control-allow-origin" not in response.headers


async def test_bearer_gate_duplicates_and_lifespan() -> None:
    observed: list[str] = []

    async def inner(scope: Any, receive: Any, send: Any) -> None:
        observed.append(scope["type"])

    gate = BearerGate(inner, TOKEN)

    async def receive() -> Any:
        return {"type": "http.request", "body": b""}

    messages: list[Any] = []

    async def send(message: Any) -> None:
        messages.append(message)

    await gate({"type": "lifespan"}, receive, send)
    await gate(
        {"type": "http", "headers": [(b"authorization", b"bearer " + TOKEN.encode())]},
        receive,
        send,
    )
    assert observed == ["lifespan", "http"]
    duplicate = [(b"authorization", b"Bearer " + TOKEN.encode())] * 2
    await gate({"type": "http", "headers": duplicate}, receive, send)
    assert messages[0]["status"] == 401


def test_http_factory_rejects_stdio(config: ServerConfig) -> None:
    with pytest.raises(ConfigurationError):
        create_http_app(create_server(config), config.server)
