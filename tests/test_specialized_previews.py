"""Real-client mock HTTP mappings and actual MCP protocol coverage; no broker access."""

import json
import os
import sys
from copy import deepcopy
from decimal import Decimal, localcontext
from typing import Any, Literal

import httpx
import pytest
from etrade_python import ETradeSettings, PlaceOrderRequest, PreviewOrderResponse
from mcp import Client
from mcp.client.stdio import StdioServerParameters
from pydantic import ValidationError

from etrade_mcp.config import ConfigurationError, ServerConfig
from etrade_mcp.guidance import described_input_schema
from etrade_mcp.order_families import ButterflyRequest, EquityRequest
from etrade_mcp.server import create_server
from etrade_mcp.tools import preview_tools
from tests.helpers import DEFAULT_TOOLS, SPECIALIZED_TOOLS, authenticated_http, http_server
from tests.preview_cases import PREVIEW_RESPONSE
from tests.response_contract_worker import client_factory
from tests.specialized_cases import CASES
from tests.test_reads import broker_factory
from tests.test_server import payload

SPECIALIZATIONS = {spec.name: spec for spec in preview_tools() if spec.name in SPECIALIZED_TOOLS}


def family_name(name: str) -> str:
    return name.removeprefix("orders_preview_").removeprefix("change_")


def args_for(name: str, case: dict[str, Any]) -> dict[str, Any]:
    arguments = deepcopy(case["arguments"])
    if "change_" in name:
        arguments["order_id"] = 17
    return arguments


@pytest.mark.parametrize("wire", ["http", "stdio"])
@pytest.mark.parametrize("mode", ["auto", "legacy"])
async def test_specialized_protocol_mapping_and_schemas(
    broker: ETradeSettings, wire: str, mode: Literal["auto", "legacy"]
) -> None:
    expected_preview = PreviewOrderResponse.model_validate(
        PREVIEW_RESPONSE["PreviewOrderResponse"]
    ).model_dump(mode="json", by_alias=True)

    async def check(client: Client) -> None:
        discovered = {tool.name: tool for tool in (await client.list_tools()).tools}
        assert discovered.keys() == DEFAULT_TOOLS
        for name, spec in SPECIALIZATIONS.items():
            assert discovered[name].input_schema == described_input_schema(name, spec.input_model)
            annotation = discovered[name].annotations
            assert annotation and not annotation.destructive_hint and not annotation.read_only_hint
            for case in CASES[family_name(name)]:
                result = await client.call_tool(name, args_for(name, case))
                assert not result.is_error, result.model_dump_json()
                data = payload(result)["data"]
                assert data["broker_preview"] == expected_preview
                expected: dict[str, Any] = {
                    "account_id_key": "synthetic-key",
                    "request": {
                        **case["canonical_preview_request"],
                        "PreviewIds": [{"previewId": 101}, {"previewId": 102}],
                    },
                }
                if "change_" in name:
                    expected["order_id"] = 17
                assert data["placement_arguments"] == expected
                await client.session.validate_tool_result(name, result)

            invalid = args_for(name, CASES[family_name(name)][0])
            invalid["request"]["approved"] = "fake-private-input"
            result = await client.call_tool(name, invalid)
            assert result.is_error and payload(result)["error"]["code"] == "invalid_input"
            assert "fake-private-input" not in result.model_dump_json()
            await client.session.validate_tool_result(name, result)

    if wire == "http":
        async with http_server(broker, client_factory=client_factory) as (url, _):
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


@pytest.mark.parametrize("name", sorted(SPECIALIZED_TOOLS))
async def test_specialized_client_dispatch_and_general_parity(
    config: ServerConfig, name: str
) -> None:
    calls: list[httpx.Request] = []
    case = CASES[family_name(name)][0]
    expected = {"PreviewOrderRequest": case["canonical_preview_request"]}

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        assert json.loads(request.content) == expected
        assert (request.method, request.url.path) == (
            ("PUT", "/v1/accounts/synthetic-key/orders/17/change/preview.json")
            if "change_" in name
            else ("POST", "/v1/accounts/synthetic-key/orders/preview.json")
        )
        return httpx.Response(200, json=PREVIEW_RESPONSE)

    async with Client(create_server(config, client_factory=broker_factory(handler))) as client:
        specialized = await client.call_tool(name, args_for(name, case))
        assert not specialized.is_error
        assert len(calls) == 1
        general_args = {
            "account_id_key": "synthetic-key",
            "request": expected["PreviewOrderRequest"],
        }
        if "change_" in name:
            general_args["order_id"] = 17
        general = await client.call_tool(
            "orders_preview_change" if "change_" in name else "orders_preview", general_args
        )
        assert not general.is_error and len(calls) == 2
        assert payload(specialized)["data"] == payload(general)["data"]
        # Canonical arguments round-trip through the actual public placement model,
        # but no placement endpoint is invoked.
        actual = payload(specialized)["data"]["placement_arguments"]["request"]
        assert (
            PlaceOrderRequest.model_validate(actual).request_body()["PlaceOrderRequest"] == actual
        )


INVALID_FIELDS: list[tuple[str, Any]] = [
    ("symbol", " "),
    ("client_order_id", "not-valid!"),
    ("client_order_id", "a" * 21),
    ("limit_price", ""),
    ("limit_price", "NaN"),
    ("limit_price", "Infinity"),
    ("limit_price", "0"),
    ("limit_price", "-1"),
    ("limit_price", 1.25),
    ("price_type", "UNKNOWN"),
    ("market_session", ""),
    ("order_term", "FILL_OR_KILL"),
    ("approved", True),
]


@pytest.mark.parametrize("family", CASES)
@pytest.mark.parametrize("key,value", INVALID_FIELDS)
def test_specialized_invalid_common_fields(family: str, key: str, value: Any) -> None:
    spec = SPECIALIZATIONS[f"orders_preview_{family}"]
    arguments = args_for(spec.name, CASES[family][0])
    arguments["request"][key] = value
    with pytest.raises(ValidationError):
        spec.input_model.model_validate(arguments)


@pytest.mark.parametrize("family", CASES)
def test_specialized_family_constraints(family: str) -> None:
    spec = SPECIALIZATIONS[f"orders_preview_{family}"]
    initial = args_for(spec.name, CASES[family][0])
    fields = initial["request"]
    invalid: list[dict[str, Any]] = []
    for key in fields:
        if "strike" in key:
            invalid.extend([{key: "0"}, {key: "NaN"}, {key: 10}])
    if family != "equity":
        quantity = "option_quantity" if family == "buy_write" else "quantity"
        invalid += [
            {quantity: "1.5"},
            {quantity: "0"},
            {"expiration": "2027-02-29"},
            {"expiration": "2026-1-01"},
            {"expiration": "2026-11-20T00:00:00"},
        ]
    else:
        invalid += [{"quantity": "0"}, {"quantity": "-1"}]
    if "buy_strike" in fields:
        invalid += [{"buy_strike": fields["sell_strike"]}]
    if "buy_call_strike" in fields:
        invalid += [{"buy_call_strike": fields["sell_call_strike"]}]
    ascending = {
        "butterfly": ("lower_strike", "middle_strike", "upper_strike"),
        "condor": (
            "lower_wing_strike",
            "lower_body_strike",
            "upper_body_strike",
            "upper_wing_strike",
        ),
        "iron_butterfly": ("lower_put_strike", "middle_strike", "upper_call_strike"),
        "iron_condor": (
            "lower_put_strike",
            "upper_put_strike",
            "lower_call_strike",
            "upper_call_strike",
        ),
    }.get(family)
    if ascending:
        invalid += [{ascending[0]: fields[ascending[1]]}, {ascending[-1]: fields[ascending[0]]}]
        if family in {"butterfly", "iron_butterfly"}:
            invalid += [{ascending[-1]: str(Decimal(fields[ascending[-1]]) + 1)}]
    for updates in invalid:
        arguments = deepcopy(initial)
        arguments["request"].update(updates)
        with pytest.raises(ValidationError):
            spec.input_model.model_validate(arguments)
    for order_id in (True, "17", 0, -1):
        arguments = {**initial, "order_id": order_id}
        with pytest.raises(ValidationError):
            SPECIALIZATIONS[f"orders_preview_change_{family}"].input_model.model_validate(arguments)


def test_exact_precision_defaults_and_pricing() -> None:
    base = CASES["equity"][0]["arguments"]["request"]
    for price_type, prices in [
        ("MARKET", {}),
        ("LIMIT", {"limit_price": "1.25"}),
        ("STOP", {"stop_price": "1.20"}),
        ("STOP_LIMIT", {"stop_price": "1.20", "limit_price": "1.25"}),
    ]:
        fields = {
            **base,
            "price_type": price_type,
            "limit_price": None,
            **prices,
            "all_or_none": False,
            "symbol": " syn ",
            "client_order_id": " Example1 ",
            "quantity": "0.123456789012345678901234567890123456789",
        }
        request = EquityRequest.model_validate(fields).to_preview()
        body = request.request_body()["PreviewOrderRequest"]
        detail = body["Order"][0]
        assert detail["allOrNone"] is False and detail["marketSession"] == "REGULAR"
        assert body["clientOrderId"] == "Example1"
        assert detail["Instrument"][0]["Product"]["symbol"] == "SYN"
        assert detail["Instrument"][0]["quantity"] == fields["quantity"]
        assert "stopLimitPrice" not in detail
        for key in ("limitPrice", "stopPrice"):
            assert (key in detail) == (
                key == "limitPrice"
                and "limit_price" in prices
                or key == "stopPrice"
                and "stop_price" in prices
            )
        for bad in (
            {"stop_price": "1"} if price_type in {"MARKET", "LIMIT"} else {"stop_price": None},
        ):
            with pytest.raises(ValidationError):
                EquityRequest.model_validate({**fields, **bad})
    butterfly = deepcopy(CASES["butterfly"][0]["arguments"]["request"])
    butterfly["quantity"] = "123456789012345678901234567890123456789"
    with localcontext() as context:
        context.prec = 5
        context.Emax = 2
        context.Emin = -2
        detail = ButterflyRequest.model_validate(butterfly).to_preview().orders[0]
    assert detail.instruments[1].quantity == Decimal("246913578024691357802469135780246913578")


@pytest.mark.parametrize("name", sorted(SPECIALIZED_TOOLS))
async def test_specialized_errors_are_sanitized_and_never_retried(
    config: ServerConfig, name: str
) -> None:
    status = 400
    calls: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        if status == 0:
            raise httpx.ReadTimeout("fake-private-timeout", request=request)
        if status == 200:
            return httpx.Response(200, json={"PreviewOrderResponse": {"PreviewIds": []}})
        if status == 201:
            return httpx.Response(
                200, json={"PreviewOrderResponse": {"PreviewIds": [{"previewId": True}]}}
            )
        return httpx.Response(
            status,
            headers={"Retry-After": "0"},
            json={
                "Error": {
                    "code": "100",
                    "message": "Synthetic broker rejection.",
                    "private": "fake-private-broker-detail",
                }
            },
        )

    async with Client(create_server(config, client_factory=broker_factory(handler))) as client:
        for failure in [
            (400, "broker_rejection"),
            (401, "authentication_failed"),
            (429, "rate_limited"),
            (503, "service_unavailable"),
            (0, "transport_error"),
            (200, "invalid_broker_response"),
            (201, "invalid_broker_response"),
        ]:
            status, code = failure
            count = len(calls)
            result = await client.call_tool(name, args_for(name, CASES[family_name(name)][0]))
            assert result.is_error and payload(result)["error"]["code"] == code
            assert len(calls) == count + 1
            assert payload(result)["error"]["broker_message"] == (
                "Synthetic broker rejection." if status >= 400 else None
            )
            assert "fake-private" not in result.model_dump_json()
            await client.session.validate_tool_result(name, result)
        count = len(calls)
        invalid = args_for(name, CASES[family_name(name)][0])
        invalid["request"]["symbol"] = " "
        result = await client.call_tool(name, invalid)
        assert result.is_error and payload(result)["error"]["code"] == "invalid_input"
        assert len(calls) == count


@pytest.mark.parametrize("wire", ["http", "stdio"])
@pytest.mark.parametrize(
    "allowlist", ["", "market_get_quote", "orders_preview_equity,orders_preview_change_iron_condor"]
)
async def test_specialized_allowlists_and_hidden_invocation(
    broker: ETradeSettings, wire: str, allowlist: str
) -> None:
    expected: set[str] = set(allowlist.split(",")) if allowlist else set()

    async def check(client: Client) -> None:
        assert {tool.name for tool in (await client.list_tools()).tools} == expected
        for name in SPECIALIZED_TOOLS:
            result = await client.call_tool(name, args_for(name, CASES[family_name(name)][0]))
            if name in expected:
                assert not result.is_error, result.model_dump_json()
                await client.session.validate_tool_result(name, result)
            else:
                assert result.is_error and payload(result)["error"]["code"] == "tool_not_available"

    if wire == "http":
        async with http_server(
            broker,
            client_factory=client_factory,
            tool_allowlist=allowlist,
            enable_order_execution=True,
            enable_alert_deletion=True,
        ) as (url, _):
            async with Client(authenticated_http(url)) as client:
                await check(client)
    else:
        environment = {
            **os.environ,
            "ETRADE_MCP_ENABLE_ORDER_EXECUTION": "true",
            "ETRADE_MCP_ENABLE_ALERT_DELETION": "true",
        }
        async with Client(
            StdioServerParameters(
                command=sys.executable,
                args=["-m", "tests.response_contract_worker", f"--tool-allowlist={allowlist}"],
                env=environment,
            )
        ) as client:
            await check(client)


def test_specialized_unknown_allowlist_fails_startup(config: ServerConfig) -> None:
    settings = config.server.model_copy(update={"tool_allowlist": "orders_preview_unknown"})
    with pytest.raises(ConfigurationError):
        create_server(config.model_copy(update={"server": settings}))
