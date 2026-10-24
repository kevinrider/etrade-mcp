import asyncio
import json
from typing import Any, Literal

import httpx2
import pytest
from etrade_python import ETradeSettings
from mcp import Client
from mcp.types import (
    CLIENT_CAPABILITIES_META_KEY,
    PROTOCOL_VERSION_META_KEY,
    UNSUPPORTED_PROTOCOL_VERSION,
)
from pydantic import SecretStr
from starlette.testclient import TestClient
from starlette.types import Message, Receive, Scope, Send

from etrade_mcp.config import ConfigurationError, ServerConfig, ServerSettings
from etrade_mcp.http import BearerGate, ProtocolErrorSanitizer, create_http_app
from etrade_mcp.server import create_server
from tests.conftest import memory_client
from tests.helpers import DEFAULT_TOOLS, TOKEN, authenticated_http, http_server
from tests.test_server import payload


@pytest.mark.parametrize("mode", ["auto", "legacy"])
async def test_actual_http_discovery_invocation_and_concurrency(
    broker: ETradeSettings, mode: Literal["auto", "legacy"]
) -> None:
    async with http_server(broker) as (url, _):
        async with Client(authenticated_http(url), mode=mode) as client:
            tools = (await client.list_tools()).tools
            assert {t.name for t in tools} == DEFAULT_TOOLS
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


@pytest.mark.parametrize("port", [80, 8000])
@pytest.mark.parametrize(
    "host,authorities",
    [
        ("127.0.0.1", ("127.0.0.1", "localhost")),
        ("::1", ("[::1]", "localhost")),
        ("0:0:0:0:0:0:0:1", ("[0:0:0:0:0:0:0:1]", "[::1]", "localhost")),
    ],
)
def test_http_accepts_default_ports_and_canonical_ipv6(
    broker: ETradeSettings, host: str, authorities: tuple[str, ...], port: int
) -> None:
    settings = ServerSettings(host=host, port=port, http_bearer_token=SecretStr(TOKEN))
    config = ServerConfig(server=settings, broker=broker)
    server = create_server(config, client_factory=memory_client)
    app = create_http_app(server, settings)
    request = {"jsonrpc": "2.0", "id": 1, "method": "tools/list"}
    headers = {"Authorization": "Bearer " + TOKEN, "Accept": "application/json, text/event-stream"}

    # Drive the real lifespan without port binding. Generate the natural Host
    # with the production HTTP client to exercise normal URL serialization
    # alongside the explicit header spellings below.
    natural_host = httpx2.Request("POST", f"http://{authorities[0]}:{port}/mcp").headers["host"]
    with TestClient(app, base_url=f"http://localhost:{port}") as http:
        natural = http.post("/mcp", headers={**headers, "Host": natural_host}, json=request)
        assert natural.status_code == 200
        assert {tool["name"] for tool in natural.json()["result"]["tools"]} == DEFAULT_TOOLS
        allowed = [f"{authority}:{port}" for authority in authorities]
        if port == 80:
            allowed.extend(authorities)
        for authority in allowed:
            for origin in (None, f"http://{authority}"):
                explicit = {**headers, "Host": authority}
                if origin is not None:
                    explicit["Origin"] = origin
                response = http.post("/mcp", headers=explicit, json=request)
                assert response.status_code == 200, (authority, origin, response.text)


@pytest.mark.parametrize("port", [80, 8000])
@pytest.mark.parametrize(
    "host,authority,other",
    [
        ("127.0.0.1", "127.0.0.1", "127.0.0.2"),
        ("::1", "[::1]", "127.0.0.1"),
        ("0:0:0:0:0:0:0:1", "[::1]", "127.0.0.1"),
    ],
)
def test_http_authority_normalization_keeps_access_restricted(
    broker: ETradeSettings, host: str, authority: str, other: str, port: int
) -> None:
    settings = ServerSettings(host=host, port=port, http_bearer_token=SecretStr(TOKEN))
    config = ServerConfig(server=settings, broker=broker)
    server = create_server(config, client_factory=memory_client)
    app = create_http_app(server, settings)
    request = {"jsonrpc": "2.0", "id": 1, "method": "tools/list"}
    headers = {"Authorization": "Bearer " + TOKEN, "Accept": "application/json, text/event-stream"}
    denied = [
        ({"Host": "evil.example"}, 421),
        ({"Host": f"localhost.evil.example:{port}"}, 421),
        ({"Host": f"{authority}:{port + 1}"}, 421),
        ({"Host": f"localhost:{port + 1}"}, 421),
        ({"Host": f"{other}:{port}"}, 421),
        ({"Origin": f"https://{authority}:{port}"}, 403),
        ({"Origin": f"http://{authority}:{port + 1}"}, 403),
        ({"Origin": f"http://{other}:{port}"}, 403),
        ({"Origin": f"http://localhost.evil.example:{port}"}, 403),
    ]
    if port != 80:
        denied.extend(
            [
                ({"Host": authority}, 421),
                ({"Origin": f"http://{authority}"}, 403),
            ]
        )
    with TestClient(app, base_url=f"http://localhost:{port}") as http:
        missing = http.post("/mcp", json=request)
        assert missing.status_code == 401
        assert missing.headers["WWW-Authenticate"] == "Bearer"
        wrong = http.post(
            "/mcp", headers={**headers, "Authorization": "Bearer wrong"}, json=request
        )
        assert wrong.status_code == 401
        for override, expected in denied:
            response = http.post("/mcp", headers={**headers, **override}, json=request)
            assert response.status_code == expected, (override, response.text)


@pytest.mark.parametrize("protocol", [None, "2025-11-25", "2026-07-28"])
@pytest.mark.parametrize(
    "body,parse_error",
    [
        ('{"private":"fake-private-pii"', True),
        (
            json.dumps(
                {
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "tools/call",
                    "params": ["fake-private-pii", TOKEN, "fake-broker-secret"],
                }
            ),
            False,
        ),
        ('{"jsonrpc":"fake-private-pii","id":1,"method":"tools/list"}', False),
        ('{"jsonrpc":"2.0","id":1,"method":{"private":"fake-private-pii"}}', False),
    ],
)
async def test_malformed_http_protocol_errors_are_sanitized(
    broker: ETradeSettings,
    caplog: pytest.LogCaptureFixture,
    protocol: str | None,
    body: str,
    parse_error: bool,
) -> None:
    headers = {
        "Authorization": "Bearer " + TOKEN,
        "Accept": "application/json, text/event-stream",
        "Content-Type": "application/json",
    }
    if protocol is not None:
        headers["MCP-Protocol-Version"] = protocol
    code = -32700 if parse_error else (-32600 if protocol == "2026-07-28" else -32602)
    message = (
        "Parse error."
        if parse_error
        else ("Invalid request." if code == -32600 else "Invalid request parameters.")
    )
    async with http_server(broker) as (url, _):
        async with httpx2.AsyncClient(trust_env=False) as http:
            response = await http.post(url, headers=headers, content=body)
            assert response.status_code == 400
            assert response.json() == {
                "jsonrpc": "2.0",
                "id": None,
                "error": {"code": code, "message": message},
            }
            assert int(response.headers["content-length"]) == len(response.content)
            # Sanitization must not disrupt the next valid request.
            async with Client(
                authenticated_http(url), mode="auto" if protocol == "2026-07-28" else "legacy"
            ) as client:
                assert {tool.name for tool in (await client.list_tools()).tools} == DEFAULT_TOOLS
    for secret in ("fake-private-pii", TOKEN, broker.consumer_secret.get_secret_value()):
        assert secret not in response.text
        assert secret not in caplog.text


async def test_protocol_sanitizer_preserves_version_negotiation(broker: ETradeSettings) -> None:
    version = "2099-01-01"
    async with http_server(broker) as (url, _):
        async with httpx2.AsyncClient(trust_env=False) as http:
            response = await http.post(
                url,
                headers={
                    "Authorization": "Bearer " + TOKEN,
                    "Accept": "application/json, text/event-stream",
                    "MCP-Protocol-Version": version,
                    "MCP-Method": "server/discover",
                },
                json={
                    "jsonrpc": "2.0",
                    "id": 7,
                    "method": "server/discover",
                    "params": {
                        "_meta": {
                            PROTOCOL_VERSION_META_KEY: version,
                            CLIENT_CAPABILITIES_META_KEY: {},
                        }
                    },
                },
            )
            assert response.status_code == 400
            result = response.json()
            assert result["id"] == 7
            assert result["error"]["code"] == UNSUPPORTED_PROTOCOL_VERSION
            assert result["error"]["data"]["requested"] == version
            assert "2026-07-28" in result["error"]["data"]["supported"]


@pytest.mark.parametrize("denial", ["authorization", "host", "origin"])
async def test_http_access_checks_precede_protocol_errors(
    broker: ETradeSettings, denial: str
) -> None:
    headers = {
        "Authorization": "Bearer " + TOKEN,
        "Accept": "application/json, text/event-stream",
        "Content-Type": "application/json",
    }
    if denial == "authorization":
        headers.pop("Authorization")
    elif denial == "host":
        headers["Host"] = "evil.example"
    else:
        headers["Origin"] = "https://evil.example"
    async with http_server(broker) as (url, _):
        async with httpx2.AsyncClient(trust_env=False) as http:
            response = await http.post(url, headers=headers, content='["fake-private-pii"')
            assert (
                response.status_code == {"authorization": 401, "host": 421, "origin": 403}[denial]
            )
            assert "fake-private-pii" not in response.text
            if denial == "authorization":
                assert response.headers["WWW-Authenticate"] == "Bearer"


@pytest.mark.parametrize(
    "body,code,request_id,message",
    [
        (
            b'{"jsonrpc":"2.0","id":"request-7","error":{"code":-32602,'
            b'"message":"fake-private-pii","data":{"secret":"fake-private-pii"}}}',
            -32602,
            "request-7",
            "Invalid request parameters.",
        ),
        (b"fake-private-pii", -32600, None, "Invalid request."),
        (b'{"private":"fake-private-pii"}', -32600, None, "Invalid request."),
    ],
)
async def test_protocol_sanitizer_handles_fragmented_and_unrecognized_errors(
    body: bytes, code: int, request_id: str | int | None, message: str
) -> None:
    observed: list[Message] = []

    async def send(event: Message) -> None:
        observed.append(event)

    async def receive() -> Message:
        raise AssertionError("Response sanitizer must not read the request")

    async def inner(scope: Scope, receive: Receive, send: Send) -> None:
        await send(
            {
                "type": "http.response.start",
                "status": 400,
                "headers": [
                    (b"content-type", b"Application/JSON; charset=utf-8"),
                    (b"Content-Length", str(len(body)).encode()),
                    (b"mcp-protocol-version", b"2026-07-28"),
                ],
            }
        )
        for fragment in (body[:1], body[1:-1]):
            await send({"type": "http.response.body", "body": fragment, "more_body": True})
            assert observed == []
        await send({"type": "http.response.body", "body": body[-1:]})

    await ProtocolErrorSanitizer(inner)({"type": "http"}, receive, send)
    assert len(observed) == 2
    result = observed[1]["body"]
    assert json.loads(result) == {
        "jsonrpc": "2.0",
        "id": request_id,
        "error": {"code": code, "message": message},
    }
    assert b"fake-private-pii" not in result
    headers = dict(observed[0]["headers"])
    assert headers[b"content-length"] == str(len(result)).encode()
    assert headers[b"mcp-protocol-version"] == b"2026-07-28"


@pytest.mark.parametrize("scope_type", ["http", "lifespan"])
@pytest.mark.parametrize("status,content_type", [(200, b"application/json"), (400, b"text/plain")])
async def test_protocol_sanitizer_passes_other_traffic_without_buffering(
    scope_type: str, status: int, content_type: bytes
) -> None:
    observed: list[Message] = []

    async def send(event: Message) -> None:
        observed.append(event)

    async def receive() -> Message:
        raise AssertionError("Response sanitizer must not read the request")

    async def inner(scope: Scope, receive: Receive, send: Send) -> None:
        if scope_type == "lifespan":
            await send({"type": "lifespan.startup.complete"})
            assert observed == [{"type": "lifespan.startup.complete"}]
            return
        events: list[Message] = [
            {
                "type": "http.response.start",
                "status": status,
                "headers": [(b"content-type", content_type)],
            },
            {"type": "http.response.body", "body": b"x" * 100_000, "more_body": True},
            {"type": "http.response.body", "body": b"last"},
        ]
        for index, event in enumerate(events):
            await send(event)
            assert observed == events[: index + 1]

    await ProtocolErrorSanitizer(inner)({"type": scope_type}, receive, send)
