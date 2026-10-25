"""Safe validation guidance through actual MCP boundaries, without broker access."""

import logging
import os
import sys
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from decimal import Decimal
from pathlib import Path
from typing import Annotated, Any, Literal

import httpx
import pytest
from etrade_python import ETradeResponseError, ETradeSettings, ETradeValidationError
from mcp import Client
from mcp.client.stdio import StdioServerParameters, stdio_client
from pydantic import BaseModel, ConfigDict, Field, ValidationError, create_model, field_validator
from pydantic_core import PydanticCustomError

from etrade_mcp.responses import classified_error
from etrade_mcp.tools.orders import OrdersPreviewInput
from etrade_mcp.tools.specialized import OrdersPreviewEquityInput
from etrade_mcp.validation import (
    Node,
    ValidationIssue,
    project_path,
    translate,
    validation_diagnostics,
)
from tests.helpers import authenticated_http, http_server
from tests.test_reads import broker_factory
from tests.test_server import payload
from tests.validation_cases import CASES, PRIVATE, equity
from tests.validation_worker import validation_tools


def diagnostics(model: type[BaseModel], arguments: Any) -> list[ValidationIssue]:
    with pytest.raises(ValidationError) as caught:
        model.model_validate(arguments)
    return validation_diagnostics(caught.value, model)


@pytest.mark.parametrize(
    "case",
    [
        case
        for case in CASES
        if case.name not in {"client_symbol", "client_symbols", "client_account"}
    ],
    ids=lambda case: case.name,
)
def test_validation_cases(case: Any) -> None:
    model = next(spec.input_model for spec in validation_tools() if spec.name == case.tool)
    issues = diagnostics(model, case.arguments)
    assert any(issue.path == case.path and issue.code == case.code for issue in issues)
    assert PRIVATE not in " ".join(issue.model_dump_json() for issue in issues)


def test_bounds_choices_and_canonical_aliases() -> None:
    issues = diagnostics(OrdersPreviewEquityInput, equity(quantity="0"))
    assert issues[0].message == "Must be greater than 0."
    issues = diagnostics(OrdersPreviewEquityInput, equity(order_action=PRIVATE))
    assert issues[0].message == "Must be one of: BUY, SELL, SELL_SHORT, BUY_TO_COVER."
    from etrade_python import PreviewOrderRequest

    from tests.preview_cases import REQUESTS

    arguments = PreviewOrderRequest.model_validate(REQUESTS["equity"]).request_body()[
        "PreviewOrderRequest"
    ]
    arguments["Order"][0]["Instrument"][0]["quantity"] = 1
    issues = diagnostics(OrdersPreviewInput, {"account_id_key": "key", "request": arguments})
    assert issues[0].path == ["request", "orders", 0, "instruments", 0, "quantity"]
    # Every missing field is reported without rerunning the validators.
    issues = diagnostics(OrdersPreviewEquityInput, {"account_id_key": "key", "request": {}})
    assert {tuple(issue.path) for issue in issues} == {
        ("request", name)
        for name in ("client_order_id", "symbol", "order_action", "quantity", "price_type")
    }


class HostileInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    value: str

    @field_validator("value")
    @classmethod
    def hostile(cls, value: str) -> str:
        raise PydanticCustomError(f"unknown_{PRIVATE}", "Exposed {secret}", {"secret": value})


def test_unknown_messages_context_and_keys_are_not_reflected() -> None:
    issues = diagnostics(HostileInput, {"value": PRIVATE, PRIVATE: PRIVATE})
    assert [(issue.path, issue.code) for issue in issues] == [
        (["value"], "invalid_value"),
        ([], "extra_forbidden"),
    ]
    assert PRIVATE not in " ".join(issue.model_dump_json() for issue in issues)
    unknown = ETradeValidationError(PRIVATE)
    assert PRIVATE not in str(validation_diagnostics(unknown))
    # Arbitrary exception context must not become a bound or allowed-choice list.
    assert PRIVATE not in translate("greater_than", PRIVATE, [Node(str)])[1]
    assert PRIVATE not in translate("literal_error", PRIVATE, [Node(str)])[1]


def test_limits_deduplication_unions_and_chained_errors() -> None:
    class Many(BaseModel):
        numbers: list[int]

    issues = diagnostics(Many, {"numbers": [PRIVATE] * 25})
    assert len(issues) == 20 and issues[-1].code == "additional_errors"
    assert all(len(issue.message) <= 256 for issue in issues)

    class Extra(BaseModel):
        model_config = ConfigDict(extra="forbid")

    assert len(diagnostics(Extra, {f"{PRIVATE}_{i}": PRIVATE for i in range(25)})) == 1

    class Either(BaseModel):
        value: int | Decimal

    issues = diagnostics(Either, {"value": PRIVATE})
    assert all(issue.path == ["value"] for issue in issues)
    nested: type[BaseModel] = Many
    arguments: dict[str, Any] = {"numbers": [PRIVATE]}
    for index in range(20):
        nested = create_model(f"Nested{index}", child=(nested, ...))
        arguments = {"child": arguments}
    issues = diagnostics(nested, arguments)
    assert len(issues[0].path) == 16
    assert project_path(("numbers", -1, PRIVATE), Many)[0] == ["numbers"]
    assert project_path(("numbers", 0, PRIVATE), Many)[0] == ["numbers", 0]
    long_name = "field" * 20
    fields: dict[str, Any] = {long_name: (str, ...)}
    long_model = create_model("LongField", **fields)
    assert diagnostics(long_model, {})[0].path == []
    try:
        OrdersPreviewEquityInput.model_validate(equity(quantity="0"))
    except ValidationError as error:
        wrapper = ETradeValidationError(PRIVATE)
        wrapper.__cause__ = error
        failure = classified_error(wrapper, input_model=OrdersPreviewEquityInput)
        assert failure.validation_errors[0].path == ["request", "quantity"]
        assert failure.broker_message is None
        broker = ETradeResponseError(PRIVATE)
        broker.__cause__ = error
        assert classified_error(broker).validation_errors == []
    cyclic = ETradeValidationError(PRIVATE)
    cyclic.__cause__ = cyclic
    assert validation_diagnostics(cyclic)[0].code == "invalid_value"


@pytest.mark.parametrize("wire", ["http", "stdio"])
@pytest.mark.parametrize("mode", ["auto", "legacy"])
async def test_validation_over_actual_mcp(
    broker: ETradeSettings,
    wire: str,
    mode: Literal["auto", "legacy"],
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.INFO)
    calls: list[httpx.Request] = []

    def forbidden(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        raise AssertionError("Invalid inputs must not reach the broker")

    async def check(client: Client) -> None:
        discovered = {tool.name: tool for tool in (await client.list_tools()).tools}
        assert set(discovered) == {case.tool for case in CASES}
        for tool in discovered.values():
            assert tool.output_schema is not None
            field = tool.output_schema["$defs"]["Failure"]["properties"]["validation_errors"]
            assert field["maxItems"] == 20
        for case in CASES:
            result = await client.call_tool(case.tool, case.arguments)
            assert result.is_error, case.name
            error = payload(result)["error"]
            assert error["code"] == "invalid_input", (case.name, error)
            assert error["broker_message"] is None
            assert any(
                issue["path"] == case.path and issue["code"] == case.code
                for issue in error["validation_errors"]
            ), (case.name, error)
            assert PRIVATE not in result.model_dump_json()
            await client.session.validate_tool_result(case.tool, result)
        assert calls == []

    if wire == "http":
        async with http_server(
            broker, tools=validation_tools(), client_factory=broker_factory(forbidden)
        ) as (url, _):
            async with Client(authenticated_http(url), mode=mode) as client:
                await check(client)
    else:
        path = tmp_path / "stderr"
        with path.open("w+") as stderr:

            @asynccontextmanager
            async def connection() -> AsyncGenerator[tuple[Any, Any]]:
                async with stdio_client(
                    StdioServerParameters(
                        command=sys.executable,
                        args=["-m", "tests.validation_worker"],
                        env=os.environ.copy(),
                    ),
                    errlog=stderr,
                ) as streams:
                    yield streams

            async with Client(connection(), mode=mode) as client:
                await check(client)
        assert PRIVATE not in path.read_text()
    assert PRIVATE not in caplog.text


def test_builtin_bounds_formats_and_trusted_metadata() -> None:
    class Bounded(BaseModel):
        value: int = Field(ge=2, le=4)
        text: str = Field(min_length=2, max_length=4)
        items: list[int] = Field(min_length=2, max_length=4)
        price: Decimal = Field(lt=10)
        flag: bool
        tag: str = Field(pattern="^[A-Z]+$")

    valid = {"value": 3, "text": "abc", "items": [1, 2], "price": "1", "flag": True, "tag": "ABC"}
    for update, code, guidance in [
        ({"value": 1}, "greater_than_equal", "2"),
        ({"value": 5}, "less_than_equal", "4"),
        ({"price": "10"}, "less_than", "10"),
        ({"text": "a"}, "string_too_short", "2"),
        ({"text": "abcde"}, "string_too_long", "4"),
        ({"items": [1]}, "too_short", "2"),
        ({"items": [1] * 5}, "too_long", "4"),
        ({"flag": PRIVATE}, "bool_parsing", "boolean"),
        ({"tag": PRIVATE}, "string_pattern_mismatch", "format"),
    ]:
        issues = diagnostics(Bounded, {**valid, **update})
        assert issues[0].code == code and guidance in issues[0].message

    class ItemBound(BaseModel):
        items: list[Annotated[int, Field(gt=0)]]

    assert diagnostics(ItemBound, {"items": [0]})[0].message == "Must be greater than 0."
    from etrade_mcp.validation import constraint

    assert constraint([Node(str, (Field(ge=1).metadata[0],))], "ge") == "1"

    class Infinite:
        gt = float("inf")

    class Nan:
        gt = Decimal("NaN")

    class Huge:
        gt = 10**5000

    assert constraint([Node(str, (Infinite(), Nan(), Huge()))], "gt") is None

    class LongDecimal:
        gt = Decimal("1234567890123456789012345678901234567890")

    assert constraint([Node(str, (LongDecimal(),))], "gt") is None
    assert (
        translate("value_error", "Value error, price_type must be one of: PRIVATE", [Node(str)])[0]
        == "unsupported_choice"
    )
    assert (
        translate("value_error", "Value error, Unsupported option category", [Node(str)])[0]
        == "unsupported_choice"
    )


def test_plain_client_reasons_and_request_only_causes() -> None:
    from etrade_mcp.tools.orders import OrdersPreviewChangeInput

    for reason, field in [
        ("account_id_key is required", "account_id_key"),
        ("order_id must be a positive integer", "order_id"),
    ]:
        issue = validation_diagnostics(ETradeValidationError(reason), OrdersPreviewChangeInput)[0]
        assert issue.path == [field]
        assert PRIVATE not in issue.message
    from copy import deepcopy

    from etrade_mcp.inputs import PreviewRequest
    from tests.preview_cases import REQUESTS

    request = deepcopy(REQUESTS["equity"])
    request["orders"][0].pop("limit_price")
    with pytest.raises(ValidationError) as caught:
        PreviewRequest.model_validate(request)
    error = ETradeValidationError(PRIVATE)
    error.__cause__ = caught.value
    issues = validation_diagnostics(error, OrdersPreviewInput, client=True)
    assert issues[0].path == ["request", "orders", 0]
    assert issues[0].code == "limit_price_required"
    assert len(validation_diagnostics(ETradeValidationError(PRIVATE), None)) == 1
