import asyncio
import json
from datetime import UTC, datetime, timedelta
from typing import Any, Literal, cast

import httpx
import pytest
from etrade_python import (
    ETradeClient,
    ETradeCredentials,
    ETradeSettings,
    MemoryCredentialStore,
    Quote,
)
from mcp import Client
from mcp.server.mcpserver.context import Context
from mcp.types import CallToolResult
from pydantic import Field, SecretStr

from etrade_mcp.config import ConfigurationError, ServerConfig, ServerSettings
from etrade_mcp.policy import ToolPolicy
from etrade_mcp.responses import Response, WireModel
from etrade_mcp.server import (
    EmptyInput,
    Runtime,
    ToolSpec,
    create_server,
    invoke,
    server_status,
)
from tests.conftest import memory_client
from tests.helpers import authenticated_http, http_server


def payload(result: CallToolResult) -> dict[str, Any]:
    return cast(dict[str, Any], result.structured_content)


@pytest.mark.parametrize("mode", ["auto", "legacy"])
async def test_status_protocol_and_strict_schema(
    config: ServerConfig, mode: Literal["auto", "legacy"]
) -> None:
    async with Client(create_server(config, client_factory=memory_client), mode=mode) as client:
        tools = (await client.list_tools()).tools
        assert [tool.name for tool in tools] == ["server_status"]
        assert tools[0].input_schema["additionalProperties"] is False
        assert tools[0].output_schema is not None
        result = await client.call_tool("server_status")
        assert not result.is_error
        assert payload(result)["ok"]
        assert payload(result)["data"]["credential_status"] == "missing"
        assert payload(result)["data"]["result_cache_implemented"] is False
        assert payload(result)["meta"]["environment"] == "sandbox"
        assert json.loads(result.content[0].text) == payload(result)  # type: ignore[union-attr]
        invalid = await client.call_tool("server_status", {"unknown": "never-echo-input"})
        assert invalid.is_error
        assert payload(invalid)["error"]["code"] == "invalid_input"
        assert "never-echo-input" not in invalid.model_dump_json()
        unknown = await client.call_tool("nonexistent")
        assert unknown.is_error
        assert payload(unknown)["error"]["code"] == "tool_not_available"


@pytest.mark.parametrize("age,expected", [(0, "active"), (3, "expired")])
async def test_status_uses_public_local_lifecycle(
    broker: ETradeSettings, age: int, expected: str
) -> None:
    store = MemoryCredentialStore()

    def factory(settings: ETradeSettings, profile: str) -> ETradeClient:
        return ETradeClient(settings, profile=profile, credential_store=store)

    settings = ServerSettings(transport="stdio", profile="personal")
    config = ServerConfig(server=settings, broker=broker)
    when = datetime.now(UTC) - timedelta(days=age)
    async with factory(broker, "personal") as seeder:
        await seeder.session.save(
            ETradeCredentials(
                access_token=SecretStr("fake-access-token"),
                access_token_secret=SecretStr("fake-access-secret"),
                acquired_at=when,
                last_used_at=when,
            )
        )
    async with Client(create_server(config, client_factory=factory)) as client:
        result = await client.call_tool("server_status")
        assert payload(result)["data"]["credential_status"] == expected
        assert payload(result)["meta"]["profile"] == "personal"
        assert "fake-access" not in result.model_dump_json()


def test_duplicate_and_unknown_allowlists(config: ServerConfig) -> None:
    spec = ToolSpec("server_status", server_status, EmptyInput)
    with pytest.raises(ConfigurationError, match="Duplicate"):
        create_server(config, tools=[spec, spec])
    restricted = config.model_copy(
        update={"server": ServerSettings(transport="stdio", tool_allowlist="unknown")}
    )
    with pytest.raises(ConfigurationError, match="unknown"):
        create_server(restricted)


class ProbeInput(WireModel):
    symbol: str = Field(min_length=1)


async def quote_probe(symbol: str, ctx: Context[Runtime, Any]) -> Response[Quote]:
    """Test-only client-boundary probe; never registered by the production server."""
    state = ctx.request_context.lifespan_context
    return await invoke("quote_probe", state, lambda: state.client.market.get_quote(symbol))


class Confirmation(WireModel):
    accepted: bool


async def mutation_probe(ctx: Context[Runtime, Any]) -> Response[Confirmation]:
    """Test-only mutation policy probe; dispatches no broker request."""
    state = ctx.request_context.lifespan_context

    async def operation() -> Confirmation:
        return Confirmation(accepted=True)

    return await invoke("mutation_probe", state, operation)


@pytest.mark.parametrize("wire", ["memory", "http"])
@pytest.mark.parametrize(
    "allowlist,enabled,expected",
    [
        (None, False, ["quote_probe"]),
        (None, True, ["mutation_probe", "quote_probe"]),
        ("", True, []),
        ("quote_probe", True, ["quote_probe"]),
        ("mutation_probe", False, []),
    ],
)
async def test_policy_discovery_and_hidden_invocation(
    broker: ETradeSettings,
    wire: str,
    allowlist: str | None,
    enabled: bool,
    expected: list[str],
) -> None:
    specs = [
        ToolSpec("quote_probe", quote_probe, ProbeInput),
        ToolSpec("mutation_probe", mutation_probe, EmptyInput, "order_execution"),
    ]
    options: dict[str, Any] = {"tool_allowlist": allowlist, "enable_order_execution": enabled}

    async def check(client: Client) -> None:
        assert sorted(t.name for t in (await client.list_tools()).tools) == expected
        result = await client.call_tool("mutation_probe")
        assert result.is_error == ("mutation_probe" not in expected)
        if "mutation_probe" not in expected:
            assert payload(result)["error"]["code"] in {"tool_not_available", "execution_disabled"}

    if wire == "memory":
        settings = ServerSettings(transport="stdio", **options)
        async with Client(
            create_server(
                ServerConfig(server=settings, broker=broker),
                tools=specs,
                client_factory=memory_client,
            )
        ) as client:
            await check(client)
    else:
        async with http_server(broker, tools=specs, **options) as (url, _):
            async with Client(authenticated_http(url)) as client:
                await check(client)


@pytest.mark.parametrize("status", [200, 400])
async def test_adapter_to_real_client_and_error_mapping(config: ServerConfig, status: int) -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if status != 200:
            return httpx.Response(status, json={"Error": {"code": "100", "message": "fake-secret"}})
        return httpx.Response(
            200,
            json={
                "QuoteResponse": {
                    "QuoteData": [
                        {
                            "Product": {"symbol": "AAPL"},
                            "All": {"lastTrade": "1.234567890123456789"},
                        }
                    ]
                }
            },
        )

    class Auth:
        async def authenticate(self, request: httpx.Request) -> None:
            request.headers["Authorization"] = "OAuth fake"

    def factory(settings: ETradeSettings, profile: str) -> ETradeClient:
        return ETradeClient(
            settings,
            profile=profile,
            authenticator=Auth(),
            credential_store=MemoryCredentialStore(),
            http_transport=httpx.MockTransport(handler),
        )

    server = create_server(
        config, client_factory=factory, tools=[ToolSpec("quote_probe", quote_probe, ProbeInput)]
    )
    async with Client(server) as client:
        result = await client.call_tool("quote_probe", {"symbol": "aapl"})
        assert len(requests) == 1
        assert requests[0].url.path == "/v1/market/quote/AAPL.json"
        assert result.is_error == (status != 200)
        if status == 200:
            assert '"1.234567890123456789"' in result.model_dump_json()
        else:
            assert payload(result)["error"]["code"] == "broker_rejection"
            assert payload(result)["error"]["broker_code"] == "100"
            assert "fake-secret" not in result.model_dump_json()
        invalid = await client.call_tool("quote_probe", {"symbol": 1})
        assert invalid.is_error
        assert len(requests) == 1


async def test_handler_gate_errors_cancellation_and_closure(config: ServerConfig) -> None:
    events: list[str] = []

    class TrackedClient(ETradeClient):
        async def aclose(self) -> None:
            events.append("closed")
            await super().aclose()

    def factory(settings: ETradeSettings, profile: str) -> ETradeClient:
        events.append("opened")
        return TrackedClient(settings, profile=profile, credential_store=MemoryCredentialStore())

    async with Client(create_server(config, client_factory=factory)) as client:
        await asyncio.gather(*(client.call_tool("server_status") for _ in range(5)))
    assert events == ["opened", "closed"]

    async with memory_client(config.broker, "default") as client:
        state = Runtime(
            config, ToolPolicy(config.server, {"mut": "order_execution", "read": "read"}), client
        )

        async def forbidden() -> WireModel:
            pytest.fail("Disabled handler must not execute")

        assert (await invoke("mut", state, forbidden)).error is not None

        async def fails() -> WireModel:
            raise RuntimeError("never-echo-this")

        failure = await invoke("read", state, fails)
        assert failure.error is not None and failure.error.code == "internal_error"

        async def cancelled() -> WireModel:
            raise asyncio.CancelledError

        with pytest.raises(asyncio.CancelledError):
            await invoke("read", state, cancelled)


def test_alert_permission_is_independent() -> None:
    settings = ServerSettings(transport="stdio", enable_order_execution=True)
    policy = ToolPolicy(settings, {"alert": "alert_deletion", "order": "order_execution"})
    assert policy.exposed == ["order"]
    enabled = settings.model_copy(update={"enable_alert_deletion": True})
    assert ToolPolicy(enabled, policy.capabilities).exposed == ["alert", "order"]
