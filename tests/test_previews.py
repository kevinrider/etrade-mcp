import asyncio
import json
import os
import sys
from collections.abc import Sequence
from copy import deepcopy
from typing import Any, Literal, cast

import httpx
import pytest
from etrade_python import (
    Disclosure,
    ETradeClient,
    ETradeSettings,
    MemoryCredentialStore,
    MFQuantity,
    OrderDetailRequest,
    OrderInstrumentRequest,
    OrderLot,
    OrderLots,
    OrderProduct,
    PreviewOrderRequest,
    PreviewOrderResponse,
)
from mcp import Client
from mcp.client.stdio import StdioServerParameters
from pydantic import BaseModel, ValidationError

from etrade_mcp.config import ServerConfig
from etrade_mcp.inputs import (
    PreviewDetail,
    PreviewDisclosure,
    PreviewInstrument,
    PreviewLot,
    PreviewLots,
    PreviewMFQuantity,
    PreviewProduct,
    PreviewRequest,
)
from etrade_mcp.server import create_server
from etrade_mcp.tools import preview_tools
from tests.helpers import PREVIEW_TOOLS, authenticated_http, http_server
from tests.preview_cases import PREVIEW_RESPONSE, REQUESTS
from tests.response_contract_worker import client_factory
from tests.test_reads import FakeAuth, broker_factory
from tests.test_server import payload


def arguments(name: str, value: dict[str, Any], account: str = "synthetic-key") -> dict[str, Any]:
    result: dict[str, Any] = {"account_id_key": account, "request": value}
    if name == "orders_preview_change":
        result["order_id"] = 17
    return result


@pytest.mark.parametrize("wire", ["http", "stdio"])
@pytest.mark.parametrize("mode", ["auto", "legacy"])
async def test_preview_protocol_capabilities(
    broker: ETradeSettings, wire: str, mode: Literal["auto", "legacy"]
) -> None:
    expected = PreviewOrderResponse.model_validate(
        PREVIEW_RESPONSE["PreviewOrderResponse"]
    ).model_dump(mode="json", by_alias=True)

    async def check(client: Client) -> None:
        tools = {tool.name: tool for tool in (await client.list_tools()).tools}
        assert PREVIEW_TOOLS <= tools.keys()
        for name in sorted(PREVIEW_TOOLS):
            annotation = tools[name].annotations
            assert annotation is not None
            assert annotation.read_only_hint is False
            assert annotation.destructive_hint is False
            assert annotation.idempotent_hint is False
            assert annotation.open_world_hint is True
            for value in REQUESTS.values():
                # The worker's real-client MockTransport asserts the exact
                # method/path/body against the public client's reference body.
                result = await client.call_tool(name, arguments(name, value))
                assert not result.is_error, result.model_dump_json()
                assert payload(result)["data"]["broker_preview"] == expected
                placement = payload(result)["data"]["placement_arguments"]
                canonical = PreviewOrderRequest.model_validate(value).request_body()[
                    "PreviewOrderRequest"
                ]
                assert placement["request"] == {
                    **canonical,
                    "PreviewIds": [{"previewId": 101}, {"previewId": 102}],
                }
                assert placement["account_id_key"] == "synthetic-key"
                assert ("order_id" in placement) == (name == "orders_preview_change")
                if name == "orders_preview_change":
                    assert placement["order_id"] == 17
                assert (
                    payload(result)["data"]["broker_preview"]["PreviewIds"][1]["cashMargin"]
                    == "MARGIN"
                )
                await client.session.validate_tool_result(name, result)

            for account, code in [
                ("preview-reject", "broker_rejection"),
                ("preview-auth", "authentication_failed"),
                ("preview-rate", "rate_limited"),
                ("preview-down", "service_unavailable"),
                ("preview-timeout", "transport_error"),
                ("preview-broken", "invalid_broker_response"),
                ("preview-empty", "invalid_broker_response"),
                ("preview-bad-id", "invalid_broker_response"),
            ]:
                result = await client.call_tool(name, arguments(name, REQUESTS["equity"], account))
                assert result.is_error
                assert payload(result)["error"]["code"] == code
                assert "fake-private" not in result.model_dump_json()
                await client.session.validate_tool_result(name, result)
            invalid = await client.call_tool(name, arguments(name, {"approved": True}))
            assert invalid.is_error and payload(invalid)["error"]["code"] == "invalid_input"
            await client.session.validate_tool_result(name, invalid)

    if wire == "http":
        async with http_server(broker, tools=preview_tools(), client_factory=client_factory) as (
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


def test_preview_nested_field_coverage_and_schema() -> None:
    pairs = {
        PreviewRequest: PreviewOrderRequest,
        PreviewDetail: OrderDetailRequest,
        PreviewInstrument: OrderInstrumentRequest,
        PreviewProduct: OrderProduct,
        PreviewLots: OrderLots,
        PreviewLot: OrderLot,
        PreviewMFQuantity: MFQuantity,
        PreviewDisclosure: Disclosure,
    }
    covered: dict[type[BaseModel], set[str]] = {model: set() for model in pairs}

    def visit(value: Any) -> None:
        if isinstance(value, BaseModel):
            if type(value) in covered:
                covered[type(value)].update(
                    value.model_fields_set & type(value).model_fields.keys()
                )
            for name in type(value).model_fields:
                visit(getattr(value, name))
        elif isinstance(value, list):
            for item in cast(list[Any], value):
                visit(item)

    for value in REQUESTS.values():
        model = PreviewRequest.model_validate(value)
        visit(model)
        assert model.request_body() == PreviewOrderRequest.model_validate(value).request_body()
    for model, public in pairs.items():
        assert set(model.model_fields) == set(public.model_fields)
        assert covered[model] == set(public.model_fields), model.__name__
    definitions = PreviewRequest.model_json_schema(by_alias=False)["$defs"]
    assert definitions["PreviewDetail"]["additionalProperties"] is True
    assert definitions["PreviewInstrument"]["additionalProperties"] is True
    for name in (
        "PreviewProduct",
        "PreviewLot",
        "PreviewLots",
        "PreviewMFQuantity",
        "PreviewDisclosure",
    ):
        assert definitions[name]["additionalProperties"] is False
    assert {
        choice["type"]
        for choice in definitions["PreviewDetail"]["properties"]["stop_price"]["anyOf"]
    } == {"string", "null"}


def test_preview_aliases_extensions_and_client_serialization() -> None:
    for value in REQUESTS.values():
        expected = PreviewOrderRequest.model_validate(value).request_body()
        # Client JSON aliases and its singleton collection forms remain accepted.
        aliased = deepcopy(expected["PreviewOrderRequest"])
        if len(aliased["Order"]) == 1:
            aliased["Order"] = aliased["Order"][0]
            if len(aliased["Order"]["Instrument"]) == 1:
                aliased["Order"]["Instrument"] = aliased["Order"]["Instrument"][0]
        assert PreviewRequest.model_validate(aliased).request_body() == expected
    value = deepcopy(REQUESTS["all_fields"])
    detail = value["orders"][0]
    detail["broker_metadata"] = {"ignored": True}
    instrument = detail["instruments"][0]
    instrument["broker_metadata"] = {"ignored": True}
    body = PreviewRequest.model_validate(value).request_body()
    assert "broker_metadata" not in json.dumps(body)
    assert body["PreviewOrderRequest"]["Order"][0]["conditionalLink"] == detail["conditionalLink"]
    assert (
        body["PreviewOrderRequest"]["Order"][0]["Instrument"][0]["legExtension"]
        == instrument["legExtension"]
    )
    lots = instrument["lots"]["lots"]
    instrument["lots"] = {"lot": lots, "Lot": deepcopy(lots), "lots": deepcopy(lots)}
    assert PreviewRequest.model_validate(value).request_body() == body
    instrument["lots"]["Lot"] = [{"id": 99}]
    with pytest.raises(ValidationError):
        PreviewRequest.model_validate(value)


MONEY_PATHS: Sequence[tuple[str, tuple[str | int, ...]]] = (
    [
        ("all_fields", ("orders", 0, name))
        for name in ("limit_price", "stop_price", "stop_limit_price", "offset_value")
    ]
    + [
        ("all_fields", ("orders", 0, "instruments", 0, name))
        for name in ("quantity", "ordered_quantity", "reserve_quantity")
    ]
    + [
        ("all_fields", ("orders", 0, "instruments", 0, "product", "strike_price")),
        ("all_fields", ("orders", 0, "instruments", 0, "lots", "lots", 0, "size")),
        ("fund_dollar", ("orders", 0, "instruments", 0, "mf_quantity", "cash")),
        ("fund_dollar", ("orders", 0, "instruments", 0, "mf_quantity", "margin")),
    ]
)


def test_preview_rejects_numeric_and_nonfinite_money() -> None:
    for case, path in MONEY_PATHS:
        for invalid in (1, 1.25, True, "NaN", "Infinity", "-Infinity"):
            value = deepcopy(REQUESTS[case])
            target: Any = value
            for key in path[:-1]:
                target = target[key]
            target[path[-1]] = invalid
            with pytest.raises(ValidationError):
                PreviewRequest.model_validate(value)


@pytest.mark.parametrize("name", sorted(PREVIEW_TOOLS))
async def test_invalid_previews_do_not_dispatch(config: ServerConfig, name: str) -> None:
    def forbidden(request: httpx.Request) -> httpx.Response:
        pytest.fail("Invalid preview dispatched")

    server = create_server(config, tools=preview_tools(), client_factory=broker_factory(forbidden))
    invalid_values: list[dict[str, Any]] = []
    for path in [
        (),
        ("orders", 0, "instruments", 0, "product"),
        ("orders", 0, "disclosure"),
        ("orders", 0, "instruments", 0, "lots"),
        ("orders", 0, "instruments", 0, "lots", "lots", 0),
    ]:
        value = deepcopy(REQUESTS["all_fields"])
        target: Any = value
        for key in path:
            target = target[key]
        target["unknown"] = "fake-private-input"
        invalid_values.append(value)
    value = deepcopy(REQUESTS["fund_dollar"])
    value["orders"][0]["instruments"][0]["mf_quantity"]["unknown"] = True
    invalid_values.append(value)
    for path, alias, conflicting in [
        ((), "clientOrderId", "OtherId"),
        (("orders", 0), "priceType", "MARKET"),
        (("orders", 0, "instruments", 0), "orderAction", "BUY"),
        (("orders", 0, "instruments", 0, "product"), "securityType", "EQ"),
        (("orders", 0, "disclosure"), "ehDisclosureFlag", False),
    ]:
        value = deepcopy(REQUESTS["all_fields"])
        target: Any = value
        for key in path:
            target = target[key]
        target[alias] = conflicting
        invalid_values.append(value)
    invalid_overrides: list[tuple[str, Any]] = [
        ("orders", []),
        ("order_type", "UNKNOWN"),
        ("client_order_id", "bad-id!"),
    ]
    for field, invalid in invalid_overrides:
        invalid_values.append({**REQUESTS["equity"], field: invalid})
    invalid_fields: list[tuple[tuple[str | int, ...], Any]] = [
        (("orders", 0, "limit_price"), 1.25),
        (("orders", 0, "limit_price"), "0"),
        (("orders", 0, "instruments"), []),
        (("orders", 0, "instruments", 0, "quantity"), "0"),
        (("orders", 0, "instruments", 0, "order_action"), "UNKNOWN"),
        (("orders", 0, "instruments", 0, "product", "expiry_month"), 13),
        (("orders", 0, "instruments", 0, "product", "strike_price"), None),
    ]
    for path, invalid in invalid_fields:
        value = deepcopy(REQUESTS["all_fields"])
        target: Any = value
        for key in path[:-1]:
            target = target[key]
        target[path[-1]] = invalid
        invalid_values.append(value)
    invalid_calls = [arguments(name, value) for value in invalid_values]
    invalid_calls.extend(
        [
            arguments(name, REQUESTS["equity"], " "),
            {**arguments(name, REQUESTS["equity"]), "approved": True},
            {"account_id_key": "synthetic-key"},
            {"account_id_key": "synthetic-key", "request": None},
        ]
    )
    if name == "orders_preview_change":
        invalid_calls.extend(
            [
                {**arguments(name, REQUESTS["equity"]), "order_id": invalid}
                for invalid in (0, -1, True, "17", 1.5)
            ]
        )
    async with Client(server) as client:
        for value in invalid_calls:
            result = await client.call_tool(name, value)
            assert result.is_error and payload(result)["error"]["code"] == "invalid_input"
            assert "fake-private-input" not in result.model_dump_json()


@pytest.mark.parametrize("wire", ["http", "stdio"])
async def test_preview_allowlist_denies_hidden_calls(broker: ETradeSettings, wire: str) -> None:
    async def check(client: Client) -> None:
        assert {tool.name for tool in (await client.list_tools()).tools} == {"orders_preview"}
        allowed = await client.call_tool(
            "orders_preview", arguments("orders_preview", REQUESTS["equity"])
        )
        assert not allowed.is_error
        denied = await client.call_tool(
            "orders_preview_change", arguments("orders_preview_change", REQUESTS["equity"])
        )
        assert denied.is_error and payload(denied)["error"]["code"] == "tool_not_available"

    if wire == "http":
        async with http_server(
            broker,
            client_factory=client_factory,
            tools=preview_tools(),
            tool_allowlist="orders_preview",
        ) as (url, _):
            async with Client(authenticated_http(url)) as client:
                await check(client)
    else:
        async with Client(
            StdioServerParameters(
                command=sys.executable,
                args=["-m", "tests.response_contract_worker", "--tool-allowlist", "orders_preview"],
                env=os.environ.copy(),
            )
        ) as client:
            await check(client)


async def test_preview_cancellation_and_explicit_repreview(config: ServerConfig) -> None:
    started = asyncio.Event()
    calls: list[httpx.Request] = []

    async def response(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        if len(calls) == 1:
            started.set()
            await asyncio.Event().wait()
        data = deepcopy(PREVIEW_RESPONSE)
        data["PreviewOrderResponse"]["PreviewIds"] = [{"previewId": 100 + len(calls)}]
        return httpx.Response(200, json=data)

    def factory(settings: ETradeSettings, profile: str) -> ETradeClient:
        return ETradeClient(
            settings,
            profile=profile,
            credential_store=MemoryCredentialStore(),
            authenticator=FakeAuth(),
            http_transport=httpx.MockTransport(response),
        )

    for iteration in range(2):
        async with Client(
            create_server(config, tools=preview_tools(), client_factory=factory)
        ) as client:
            if iteration == 0:
                task = asyncio.create_task(
                    client.call_tool(
                        "orders_preview", arguments("orders_preview", REQUESTS["equity"])
                    )
                )
                await asyncio.wait_for(started.wait(), 5)
                task.cancel()
                with pytest.raises(asyncio.CancelledError):
                    await task
                assert len(calls) == 1
            result = await client.call_tool(
                "orders_preview", arguments("orders_preview", REQUESTS["equity"])
            )
            assert not result.is_error
            assert (
                payload(result)["data"]["broker_preview"]["PreviewIds"][0]["previewId"]
                == 102 + iteration
            )
    assert len(calls) == 3  # A restart or explicit repeat never recovers/replays a stored result.
    assert all(call.content == calls[0].content for call in calls)
