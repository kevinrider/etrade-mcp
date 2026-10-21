import copy
from collections.abc import Callable
from typing import Any, Literal

import httpx
import pytest
from etrade_python import ETradeClient, ETradeSettings, MemoryCredentialStore
from mcp import Client
from pydantic import BaseModel

from etrade_mcp.config import ServerConfig, ServerSettings
from etrade_mcp.server import ClientFactory, create_server
from tests.helpers import READ_TOOLS, authenticated_http, http_server
from tests.read_cases import CASES, ReadCase
from tests.test_server import payload


class FakeAuth:
    async def authenticate(self, request: httpx.Request) -> None:
        request.headers["Authorization"] = "OAuth fake-test-authorization"


def broker_factory(handler: Callable[[httpx.Request], httpx.Response]) -> ClientFactory:
    def factory(settings: ETradeSettings, profile: str) -> ETradeClient:
        return ETradeClient(
            settings,
            profile=profile,
            authenticator=FakeAuth(),
            credential_store=MemoryCredentialStore(),
            http_transport=httpx.MockTransport(handler),
        )

    return factory


@pytest.mark.parametrize("case", CASES, ids=lambda case: case.tool)
@pytest.mark.parametrize("wire", ["memory", "http"])
async def test_read_request_fields_reach_real_client(
    config: ServerConfig, case: ReadCase, wire: str
) -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        assert request.method == "GET"
        assert request.url.path == case.path
        assert request.url.params == httpx.QueryParams(case.params)
        if case.tool == "market_lookup_product":
            assert b"%26" in request.url.raw_path and b"%20" in request.url.raw_path
        return httpx.Response(200, json=case.payload)

    async def check(client: Client) -> None:
        result = await client.call_tool(case.tool, case.arguments)
        assert not result.is_error, result.model_dump_json()
        assert payload(result)["data"] is not None
        assert len(seen) == 1  # Broker continuation fields never trigger aggregation.
        if case.tool == "transactions_list":
            data = payload(result)["data"]
            assert data["marker"] == "next" and data["moreTransactions"] is True
            assert [t["transactionId"] for t in data["transaction"]] == ["boundary", "next"]
        if case.tool == "portfolio_get_positions":
            assert payload(result)["data"]["accountPortfolio"][0]["nextPageNo"] == "3"
        if case.tool == "orders_list":
            assert payload(result)["data"]["marker"] == "next-order"
        if case.tool not in {
            "accounts_list",
            "market_lookup_product",
            "market_get_option_expirations",
            "orders_list",
            "alerts_list",
            "alerts_get",
        }:
            assert "0.1234567890123456789" in result.model_dump_json()

    if wire == "memory":
        async with Client(create_server(config, client_factory=broker_factory(handler))) as client:
            await check(client)
    else:
        async with http_server(config.broker, client_factory=broker_factory(handler)) as (url, _):
            async with Client(authenticated_http(url)) as client:
                await check(client)


def test_request_cases_cover_public_client_fields() -> None:
    for case in CASES:
        model: type[BaseModel] | None = case.request_model
        if model is not None:
            fields = (
                case.arguments
                if case.tool == "market_lookup_product"
                else case.arguments["request"]
            )
            assert set(fields) == set(model.model_fields), case.tool
    assert {case.tool for case in CASES} == READ_TOOLS - {"server_status"}


@pytest.mark.parametrize("case", CASES, ids=lambda case: case.tool)
async def test_unknown_read_inputs_never_dispatch(config: ServerConfig, case: ReadCase) -> None:
    def forbidden(request: httpx.Request) -> httpx.Response:
        pytest.fail("Invalid inputs must not reach broker")

    async with Client(create_server(config, client_factory=broker_factory(forbidden))) as client:
        arguments = copy.deepcopy(case.arguments)
        arguments["unknown"] = "do-not-echo-private-input"
        result = await client.call_tool(case.tool, arguments)
        assert result.is_error and payload(result)["error"]["code"] == "invalid_input"
        assert "do-not-echo" not in result.model_dump_json()
        if "request" in arguments:
            del arguments["unknown"]
            arguments["request"]["unknown"] = "do-not-echo-private-input"
            result = await client.call_tool(case.tool, arguments)
            assert result.is_error and payload(result)["error"]["code"] == "invalid_input"
            assert "do-not-echo" not in result.model_dump_json()


@pytest.mark.parametrize("alias", [False, True])
async def test_supported_aliases_and_conflicts(config: ServerConfig, alias: bool) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.params["htmlTags"] == "false"
        return httpx.Response(200, json={"AlertDetailsResponse": {"id": 1}})

    async with Client(create_server(config, client_factory=broker_factory(handler))) as client:
        name = "htmlTags" if alias else "html_tags"
        result = await client.call_tool("alerts_get", {"alert_id": 1, "request": {name: False}})
        assert not result.is_error
        conflict = await client.call_tool(
            "alerts_get",
            {
                "alert_id": 1,
                "request": {"htmlTags": True, "html_tags": False},
            },
        )
        assert conflict.is_error
        equal = await client.call_tool(
            "alerts_get",
            {
                "alert_id": 1,
                "request": {"htmlTags": False, "html_tags": False},
            },
        )
        assert not equal.is_error
        schema = next(
            t for t in (await client.list_tools()).tools if t.name == "alerts_get"
        ).input_schema
        assert '"html_tags"' in str(schema).replace("'", '"')
        assert "htmlTags" not in str(schema)


@pytest.mark.parametrize(
    "arguments",
    [
        {"symbol": "AAPL", "request": {"strike_price_near": 1.5}},
        {"symbol": "AAPL", "request": {"strike_price_near": 100}},
        {"symbol": "AAPL", "request": {"strike_price_near": "NaN"}},
        {"symbol": "AAPL", "request": {"strike_price_near": "-1"}},
        {"symbol": "AAPL", "request": {"expiry_month": 13}},
    ],
)
async def test_chain_validation_before_dispatch(
    config: ServerConfig, arguments: dict[str, Any]
) -> None:
    def forbidden(request: httpx.Request) -> httpx.Response:
        pytest.fail("Invalid chain request dispatched")

    async with Client(create_server(config, client_factory=broker_factory(forbidden))) as client:
        result = await client.call_tool("market_get_option_chain", arguments)
        assert result.is_error and payload(result)["error"]["code"] == "invalid_input"


@pytest.mark.parametrize("wire", ["memory", "http"])
async def test_market_only_allowlist_blocks_private_reads(config: ServerConfig, wire: str) -> None:
    def forbidden(request: httpx.Request) -> httpx.Response:
        pytest.fail("Hidden tool dispatched")

    settings = ServerSettings(transport="stdio", tool_allowlist="market_get_quote")

    async def check(client: Client) -> None:
        assert {t.name for t in (await client.list_tools()).tools} == {
            "market_get_quote",
        }
        for name in ("accounts_list", "orders_list", "alerts_get"):
            result = await client.call_tool(name, {})
            assert result.is_error and payload(result)["error"]["code"] == "tool_not_available"

    if wire == "memory":
        async with Client(
            create_server(
                ServerConfig(server=settings, broker=config.broker),
                client_factory=broker_factory(forbidden),
            )
        ) as client:
            await check(client)
    else:
        async with http_server(
            config.broker,
            tool_allowlist=settings.tool_allowlist,
            client_factory=broker_factory(forbidden),
        ) as (url, _):
            async with Client(authenticated_http(url)) as client:
                await check(client)


@pytest.mark.parametrize(
    "case", [case for case in CASES if "request" in case.arguments], ids=lambda case: case.tool
)
@pytest.mark.parametrize("request_value", [None, {}])
async def test_default_read_request_mapping(
    config: ServerConfig, case: ReadCase, request_value: dict[str, Any] | None
) -> None:
    expected: dict[str, str] = {}
    if case.tool == "accounts_get_balance":
        expected = {"instType": "BROKERAGE", "realTimeNAV": "false"}
    elif case.tool == "transactions_list":
        expected = {"sortOrder": "DESC"}
    elif case.tool in {"market_get_option_expirations", "market_get_option_chain"}:
        expected = {"symbol": "AAPL"}

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.params == httpx.QueryParams(expected)
        return httpx.Response(200, json=case.payload)

    arguments = copy.deepcopy(case.arguments)
    arguments["request"] = request_value
    async with Client(create_server(config, client_factory=broker_factory(handler))) as client:
        result = await client.call_tool(case.tool, arguments)
        assert not result.is_error, result.model_dump_json()


async def test_order_request_aliases_and_explicit_null(config: ServerConfig) -> None:
    case = next(case for case in CASES if case.tool == "orders_list")
    request_fields = copy.deepcopy(case.arguments["request"])
    request_fields.update(
        fromDate=request_fields.pop("from_date"),
        toDate=request_fields.pop("to_date"),
        securityType=request_fields.pop("security_type"),
        transactionType=request_fields.pop("transaction_type"),
        marketSession=request_fields.pop("market_session"),
    )

    def handler(request: httpx.Request) -> httpx.Response:
        if "/orders.json" in request.url.path:
            assert request.url.params == httpx.QueryParams(case.params)
            return httpx.Response(200, json=case.payload)
        assert request.url.params == httpx.QueryParams()
        return httpx.Response(204)

    async with Client(create_server(config, client_factory=broker_factory(handler))) as client:
        result = await client.call_tool(
            "orders_list", {"account_id_key": "synthetic-key", "request": request_fields}
        )
        assert not result.is_error
        empty = await client.call_tool(
            "transactions_list",
            {
                "account_id_key": "synthetic-key",
                "request": {"sort_order": None},
            },
        )
        assert not empty.is_error
        assert payload(empty)["data"]["transaction"] == []


@pytest.mark.parametrize(
    "tool,args,key",
    [
        ("accounts_list", {}, "accounts"),
        ("portfolio_get_positions", {"account_id_key": "synthetic-key"}, "accountPortfolio"),
        ("transactions_list", {"account_id_key": "synthetic-key"}, "transaction"),
        ("alerts_list", {}, "alerts"),
    ],
)
async def test_empty_broker_reads(
    config: ServerConfig, tool: str, args: dict[str, Any], key: str
) -> None:
    async with Client(
        create_server(config, client_factory=broker_factory(lambda _: httpx.Response(204)))
    ) as client:
        result = await client.call_tool(tool, args)
        assert not result.is_error and payload(result)["data"][key] == []


@pytest.mark.parametrize(
    "status,body,expected",
    [
        (400, {"Error": {"code": "100", "message": "fake-broker-secret"}}, "broker_rejection"),
        (401, {"Error": {"message": "fake-broker-secret"}}, "authentication_failed"),
        (200, {"unrecognized": "fake-broker-secret"}, "invalid_broker_response"),
    ],
)
async def test_read_broker_failures_are_sanitized(
    config: ServerConfig, status: int, body: dict[str, Any], expected: str
) -> None:
    async with Client(
        create_server(
            config, client_factory=broker_factory(lambda _: httpx.Response(status, json=body))
        )
    ) as client:
        result = await client.call_tool("market_get_quote", {"symbol": "AAPL"})
        assert result.is_error and payload(result)["error"]["code"] == expected
        assert "fake-broker-secret" not in result.model_dump_json()


@pytest.mark.parametrize(
    "count,override,valid",
    [
        (25, False, True),
        (26, False, False),
        (50, True, True),
        (51, True, False),
    ],
)
async def test_quote_symbol_count_capability(
    config: ServerConfig, count: int, override: bool, valid: bool
) -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        assert request.url.path.count(",") == count - 1
        return httpx.Response(200, json={"QuoteResponse": {"QuoteData": []}})

    async with Client(create_server(config, client_factory=broker_factory(handler))) as client:
        result = await client.call_tool(
            "market_get_quotes",
            {
                "symbols": [f"SYN{index}" for index in range(count)],
                "request": {"override_symbol_count": override},
            },
        )
        assert bool(result.is_error) == (not valid)
        assert len(seen) == int(valid)


@pytest.mark.parametrize("mode", ["auto", "legacy"])
async def test_read_invocation_in_both_protocol_eras(
    config: ServerConfig, mode: Literal["auto", "legacy"]
) -> None:
    case = CASES[0]
    async with Client(
        create_server(
            config, client_factory=broker_factory(lambda _: httpx.Response(200, json=case.payload))
        ),
        mode=mode,
    ) as client:
        result = await client.call_tool(case.tool)
        assert not result.is_error
        assert payload(result)["data"]["accounts"][0]["accountId"] == "synthetic-account"
