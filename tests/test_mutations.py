"""Offline mutation integration: real client HTTP mapping and actual MCP messages."""

import asyncio
import json
import os
import sys
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from copy import deepcopy
from pathlib import Path
from typing import Any, Literal, cast

import httpx
import pytest
from etrade_python import ETradeSettings, PreviewOrderRequest
from jsonschema import Draft202012Validator
from mcp import Client
from mcp.client.stdio import StdioServerParameters, stdio_client

from etrade_mcp.config import ServerConfig
from etrade_mcp.server import create_server
from etrade_mcp.tool_logging import configure_tool_logging
from tests.helpers import (
    ALL_TOOLS,
    DEFAULT_TOOLS,
    ORDER_MUTATIONS,
    authenticated_http,
    http_server,
)
from tests.mutation_cases import BODY, IDS, MUTATIONS, response
from tests.preview_cases import REQUESTS
from tests.specialized_cases import CASES
from tests.test_guidance import InstanceValidator
from tests.test_reads import broker_factory
from tests.test_server import payload


def configured(config: ServerConfig, **settings: Any) -> ServerConfig:
    return config.model_copy(
        update={
            "server": config.server.model_copy(
                update={"enable_order_execution": True, "enable_alert_deletion": True, **settings}
            )
        }
    )


@pytest.mark.parametrize("mode", ["auto", "legacy"])
@pytest.mark.parametrize("wire", ["http", "stdio"])
@pytest.mark.parametrize("enabled", [False, True])
async def test_mutation_protocol_discovery_mapping_and_errors(
    broker: ETradeSettings,
    mode: Literal["auto", "legacy"],
    wire: str,
    enabled: bool,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    sent: list[dict[str, Any]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        sent.append(
            {
                "method": request.method,
                "path": request.url.path,
                "body": json.loads(request.content) if request.content else None,
            }
        )
        return response(request)

    async def check(client: Client) -> None:
        tools = {tool.name: tool for tool in (await client.list_tools()).tools}
        assert tools.keys() == (ALL_TOOLS if enabled else DEFAULT_TOOLS)
        for case in MUTATIONS:
            if enabled:
                tool = tools[case.tool]
                assert tool.annotations and not tool.annotations.read_only_hint
                assert tool.annotations.destructive_hint and not tool.annotations.idempotent_hint
                assert tool.annotations.open_world_hint
                assert '"$ref"' not in json.dumps(tool.input_schema)
                result = await client.call_tool(case.tool, deepcopy(case.arguments))
                data = payload(result)
                assert not result.is_error and data["error"] is None
                assert data["data"] is not None
                if case.tool.startswith("orders_place"):
                    assert [item["orderId"] for item in data["data"]["OrderIds"]] == [701, 702]
                    assert data["data"]["totalCommission"] == "0.1234567890123456789"
                await client.session.validate_tool_result(case.tool, result)
                invalid = await client.call_tool(case.tool, {**case.arguments, "approved": True})
                assert invalid.is_error and payload(invalid)["error"]["code"] == "invalid_input"
            else:
                result = await client.call_tool(case.tool, case.arguments)
                assert result.is_error and payload(result)["error"]["code"] == "execution_disabled"
        if enabled:
            for ids, code in (([101, 999], "broker_rejection"), ([998], "uncertain_execution")):
                result = await client.call_tool("alerts_delete", {"alert_ids": ids})
                assert result.is_error
                data = payload(result)
                assert data["data"] is None and data["error"]["code"] == code
                assert data["error"]["alert_deletion_result"] is not None
                schema = tools["alerts_delete"].output_schema
                assert schema is not None
                cast(InstanceValidator, Draft202012Validator(schema)).validate(data)

    configure_tool_logging(True)
    try:
        if wire == "http":
            async with http_server(
                broker,
                client_factory=broker_factory(handler),
                enable_order_execution=enabled,
                enable_alert_deletion=enabled,
                debug_tool_calls=True,
            ) as (url, _):
                async with Client(authenticated_http(url), mode=mode) as client:
                    await check(client)
            stderr = capsys.readouterr().err
        else:
            record = tmp_path / "requests.jsonl"
            stderr_path = tmp_path / "server.stderr"
            with stderr_path.open("w+") as errlog:

                @asynccontextmanager
                async def connection() -> AsyncGenerator[tuple[Any, Any]]:
                    async with stdio_client(
                        StdioServerParameters(
                            command=sys.executable,
                            args=["-m", "tests.mutation_worker", "--record-path", str(record)],
                            env={
                                **os.environ,
                                "ETRADE_MCP_ENABLE_ORDER_EXECUTION": str(enabled),
                                "ETRADE_MCP_ENABLE_ALERT_DELETION": str(enabled),
                                "ETRADE_MCP_DEBUG_TOOL_CALLS": "true",
                            },
                        ),
                        errlog=errlog,
                    ) as streams:
                        yield streams

                async with Client(connection(), mode=mode) as client:
                    await check(client)
            sent = (
                [json.loads(line) for line in record.read_text().splitlines()]
                if record.exists()
                else []
            )
            stderr = stderr_path.read_text()
        expected = (
            [{"method": case.method, "path": case.path, "body": case.body} for case in MUTATIONS]
            if enabled
            else []
        )
        if enabled:
            expected.extend(
                [
                    {"method": "DELETE", "path": "/v1/user/alerts/101,999.json", "body": None},
                    {"method": "DELETE", "path": "/v1/user/alerts/998.json", "body": None},
                ]
            )
        assert sent == expected
        assert "fake-private-account-response" not in stderr
        assert "fake-broker-secret" not in stderr
        assert "Synthetic acceptance warning" not in stderr
        assert "OAuth fake-test-authorization" not in stderr
    finally:
        configure_tool_logging(False)


@pytest.mark.parametrize(
    "orders,alerts", [(False, False), (True, False), (False, True), (True, True)]
)
@pytest.mark.parametrize("allowlist", [None, "", "orders_place,alerts_delete", "server_status"])
async def test_permission_intersection_and_zero_dispatch(
    config: ServerConfig, orders: bool, alerts: bool, allowlist: str | None
) -> None:
    sent: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        sent.append(request)
        return response(request)

    settings = configured(
        config,
        enable_order_execution=orders,
        enable_alert_deletion=alerts,
        tool_allowlist=allowlist,
    )
    allowed = (
        DEFAULT_TOOLS
        | (ORDER_MUTATIONS if orders else set[str]())
        | ({"alerts_delete"} if alerts else set[str]())
    )
    if allowlist is not None:
        allowed &= set(allowlist.split(",")) if allowlist else set()
    async with Client(create_server(settings, client_factory=broker_factory(handler))) as client:
        assert {tool.name for tool in (await client.list_tools()).tools} == allowed
        for case in MUTATIONS:
            if case.tool not in allowed:
                result = await client.call_tool(case.tool, case.arguments)
                assert result.is_error
                expected = (
                    "tool_not_available"
                    if allowlist is not None and case.tool not in allowlist.split(",")
                    else "execution_disabled"
                )
                assert payload(result)["error"]["code"] == expected
    assert sent == []


@pytest.mark.parametrize("change", [False, True])
async def test_every_preview_family_round_trips_without_reconstruction(
    config: ServerConfig, change: bool
) -> None:
    sent: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        sent.append(request)
        return response(request)

    async with Client(
        create_server(configured(config), client_factory=broker_factory(handler))
    ) as client:
        for family, cases in CASES.items():
            for case in cases:
                arguments = deepcopy(case["arguments"])
                if change:
                    arguments["order_id"] = 17
                preview = await client.call_tool(
                    f"orders_preview_{'change_' if change else ''}{family}", arguments
                )
                assert not preview.is_error, preview.model_dump_json()
                placement = payload(preview)["data"]["placement_arguments"]
                expected = {**case["canonical_preview_request"], "PreviewIds": IDS}
                assert placement["request"] == expected
                result = await client.call_tool(
                    "orders_place_change" if change else "orders_place", placement
                )
                assert not result.is_error, result.model_dump_json()
                assert json.loads(sent[-1].content) == {"PlaceOrderRequest": expected}
                assert sent[-1].url.path.endswith(
                    "/17/change/place.json" if change else "/orders/place.json"
                )
        assert len(sent) == 2 * sum(map(len, CASES.values()))


@pytest.mark.parametrize("change", [False, True])
async def test_general_requests_preserve_all_supported_fields(
    config: ServerConfig, change: bool
) -> None:
    sent: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        sent.append(request)
        return response(request)

    async with Client(
        create_server(configured(config), client_factory=broker_factory(handler))
    ) as client:
        for request in REQUESTS.values():
            args: dict[str, Any] = {"account_id_key": "synthetic-key", "request": deepcopy(request)}
            if change:
                args["order_id"] = 17
            preview = await client.call_tool(
                "orders_preview_change" if change else "orders_preview", args
            )
            assert not preview.is_error
            expected = {
                **PreviewOrderRequest.model_validate(request).request_body()["PreviewOrderRequest"],
                "PreviewIds": IDS,
            }
            args = payload(preview)["data"]["placement_arguments"]
            assert args["request"] == expected
            placed = await client.call_tool(
                "orders_place_change" if change else "orders_place", args
            )
            assert not placed.is_error, placed.model_dump_json()
            assert json.loads(sent[-1].content) == {"PlaceOrderRequest": expected}
        assert len(sent) == len(REQUESTS) * 2


def invalid_arguments() -> list[tuple[str, dict[str, Any]]]:
    values: list[tuple[str, dict[str, Any]]] = []
    requests: list[Any] = [
        {},
        {**BODY, "PreviewIds": []},
        {**BODY, "PreviewIds": [{"previewId": True}]},
        {**BODY, "PreviewIds": [{"previewId": 0}]},
        {**BODY, "preview_ids": [{"preview_id": 9}]},
        {**BODY, "PreviewIds": [{"previewId": 101, "preview_id": 102}]},
        {**BODY, "PreviewIds": [{"previewId": 101, "approved": True}]},
        json.dumps(BODY),
    ]
    for request in requests:
        values.append(("orders_place", {"account_id_key": "synthetic-key", "request": request}))
    for field in ("quantity", "limitPrice"):
        request = deepcopy(BODY)
        target = (
            request["Order"][0]["Instrument"][0] if field == "quantity" else request["Order"][0]
        )
        target[field] = 1
        values.append(("orders_place", {"account_id_key": "synthetic-key", "request": request}))
    for order_id in (0, -1, True, "17"):
        values.append(("orders_cancel", {"account_id_key": "synthetic-key", "order_id": order_id}))
        values.append(
            (
                "orders_place_change",
                {"account_id_key": "synthetic-key", "order_id": order_id, "request": BODY},
            )
        )
    for alert_ids in ([], [0], [True], ["101"], 101):
        values.append(("alerts_delete", {"alert_ids": alert_ids}))
    for tool in ORDER_MUTATIONS:
        case = next(case for case in MUTATIONS if case.tool == tool)
        values.append((tool, {**case.arguments, "account_id_key": " "}))
    return values


async def test_invalid_mutations_never_dispatch(config: ServerConfig) -> None:
    sent: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        sent.append(request)
        return response(request)

    async with Client(
        create_server(configured(config), client_factory=broker_factory(handler))
    ) as client:
        for tool, args in invalid_arguments():
            result = await client.call_tool(tool, args)
            assert result.is_error, (tool, args)
            error = payload(result)["error"]
            assert error["code"] == "invalid_input"
            assert error["validation_errors"]
    assert not sent


@pytest.mark.parametrize("case", MUTATIONS, ids=lambda case: case.tool)
@pytest.mark.parametrize(
    "failure,code",
    [
        ("timeout", "uncertain_execution"),
        ("write", "uncertain_execution"),
        ("connect", "uncertain_execution"),
        ("malformed", "uncertain_execution"),
        (503, "uncertain_execution"),
        (408, "uncertain_execution"),
        (429, "rate_limited"),
        (401, "authentication_failed"),
        (400, "broker_rejection"),
    ],
)
async def test_mutation_failures_are_never_retried(
    config: ServerConfig, case: Any, failure: Any, code: str
) -> None:
    sent: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        sent.append(request)
        if failure in {"timeout", "write", "connect"}:
            error = {
                "timeout": httpx.ReadTimeout,
                "write": httpx.WriteError,
                "connect": httpx.ConnectError,
            }[failure]
            raise error("fake-private-transport-detail", request=request)
        if failure == "malformed":
            return httpx.Response(200, json={"Unknown": "fake-private-broker-detail"})
        return httpx.Response(
            failure,
            headers={"Retry-After": "0"},
            json={
                "Error": {"code": "99990", "message": "Synthetic broker message fake-broker-secret"}
            },
        )

    async with http_server(
        config.broker,
        client_factory=broker_factory(handler),
        enable_order_execution=True,
        enable_alert_deletion=True,
    ) as (url, _):
        async with Client(authenticated_http(url)) as client:
            result = await client.call_tool(case.tool, case.arguments)
            assert result.is_error
            error = payload(result)["error"]
            assert error["code"] == code
            assert error["alert_deletion_result"] is None
            assert (
                "fake-private" not in result.model_dump_json()
                and "fake-broker-secret" not in result.model_dump_json()
            )
            if isinstance(failure, int):
                assert error["broker_code"] == "99990" and error["status_code"] == failure
                assert "[REDACTED]" in error["broker_message"]
    assert len(sent) == 1


@pytest.mark.parametrize(
    "broker_result,code",
    [
        ({"result": "SUCCESS"}, None),
        ({"result": "SUCCESS", "failedAlerts": {"alertId": []}}, None),
        ({"result": "ERROR", "failedAlerts": {"alertId": [102]}}, "broker_rejection"),
        ({"result": "SUCCESS", "failedAlerts": {"alertId": [102]}}, "broker_rejection"),
        ({"result": "ERROR", "failedAlerts": {"alertId": [101, 102]}}, "broker_rejection"),
        ({"result": "ERROR"}, "broker_rejection"),
        ({"FailedAlerts": {"alertId": 102}}, "broker_rejection"),
        ({"result": "UNKNOWN"}, "uncertain_execution"),
        ({"failedAlerts": {"alertId": []}}, "uncertain_execution"),
    ],
)
async def test_alert_deletion_preserves_partial_and_unclear_results(
    config: ServerConfig, broker_result: dict[str, Any], code: str | None
) -> None:
    sent: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        sent.append(request)
        return httpx.Response(200, json={"DeleteAlertsResponse": broker_result})

    async with Client(
        create_server(configured(config), client_factory=broker_factory(handler))
    ) as client:
        tool = next(t for t in (await client.list_tools()).tools if t.name == "alerts_delete")
        result = await client.call_tool("alerts_delete", {"alert_ids": [101, 102]})
        data = payload(result)
        assert result.is_error is (code is not None)
        if code is not None:
            assert data["data"] is None and data["error"]["code"] == code
            retained = data["error"]["alert_deletion_result"]
        else:
            assert data["error"] is None
            retained = data["data"]
        from etrade_python import DeleteAlertsResponse

        assert retained == DeleteAlertsResponse.model_validate(broker_result).model_dump(
            mode="json", by_alias=True
        )
        assert tool.output_schema is not None
        cast(InstanceValidator, Draft202012Validator(tool.output_schema)).validate(data)
        await client.session.validate_tool_result("alerts_delete", result)
    assert len(sent) == 1


@pytest.mark.parametrize(
    "tool,envelope",
    [
        ("orders_place", "PlaceOrderResponse"),
        ("orders_place_change", "PlaceOrderResponse"),
        ("orders_cancel", "CancelOrderResponse"),
    ],
)
async def test_missing_order_confirmations_are_uncertain(
    config: ServerConfig, tool: str, envelope: str
) -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json={envelope: {"accountId": "fake-account"}})

    case = next(case for case in MUTATIONS if case.tool == tool)
    async with Client(
        create_server(configured(config), client_factory=broker_factory(handler))
    ) as client:
        result = await client.call_tool(tool, case.arguments)
        assert result.is_error and payload(result)["error"]["code"] == "uncertain_execution"
    assert len(seen) == 1


async def test_restart_and_explicit_concurrent_calls_do_not_deduplicate_or_replay(
    config: ServerConfig,
) -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        if len(seen) == 1:
            raise httpx.ReadTimeout("fake-lost-response", request=request)
        return response(request)

    factory = broker_factory(handler)
    args = MUTATIONS[0].arguments
    async with Client(create_server(configured(config), client_factory=factory)) as client:
        result = await client.call_tool("orders_place", args)
        assert result.is_error and payload(result)["error"]["code"] == "uncertain_execution"
    assert len(seen) == 1
    async with Client(create_server(configured(config), client_factory=factory)) as client:
        assert not (await client.call_tool("server_status")).is_error
        assert len(seen) == 1
        results = await asyncio.gather(
            client.call_tool("orders_place", args), client.call_tool("orders_place", args)
        )
        assert all(not result.is_error for result in results)
    assert len(seen) == 3
    assert all(json.loads(request.content) == {"PlaceOrderRequest": BODY} for request in seen)


async def test_mcp_client_cancellation_after_dispatch_does_not_retry(
    broker: ETradeSettings,
) -> None:
    started, stopped, release = asyncio.Event(), asyncio.Event(), asyncio.Event()
    seen: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        started.set()
        try:
            await release.wait()
        finally:
            stopped.set()
        return response(request)

    async with http_server(
        broker, client_factory=broker_factory(handler), enable_order_execution=True
    ) as (url, _):
        async with Client(authenticated_http(url)) as client:
            task = asyncio.create_task(client.call_tool("orders_place", MUTATIONS[0].arguments))
            try:
                await asyncio.wait_for(started.wait(), 5)
                task.cancel()
                with pytest.raises(asyncio.CancelledError):
                    await task
                # Losing the caller does not guarantee the broker operation
                # stops. Let the simulated broker finish its single attempt.
                release.set()
                await asyncio.wait_for(stopped.wait(), 5)
            finally:
                release.set()
                if not task.done():
                    task.cancel()
    assert len(seen) == 1


@pytest.mark.parametrize("long_text", [False, True])
async def test_deletion_error_details_redact_secrets_and_do_not_log_results(
    broker: ETradeSettings,
    capsys: pytest.CaptureFixture[str],
    long_text: bool,
) -> None:
    from tests.helpers import TOKEN

    configured_secrets = ("fake-key", "fake-broker-secret", TOKEN)

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "DeleteAlertsResponse": {
                    "result": ("x" * 1500 if long_text else "ERROR ")
                    + " ".join(configured_secrets),
                    "failedAlerts": {"alertId": [102]},
                }
            },
        )

    configure_tool_logging(True)
    try:
        async with http_server(
            broker,
            client_factory=broker_factory(handler),
            enable_alert_deletion=True,
            debug_tool_calls=True,
        ) as (url, _):
            async with Client(authenticated_http(url)) as client:
                result = await client.call_tool("alerts_delete", {"alert_ids": [101, 102]})
                assert result.is_error
                data = payload(result)
                retained = data["error"]["alert_deletion_result"]
                assert retained["failedAlerts"]["alertId"] == [102]
                assert retained["result"] == (
                    "x" * 1000 if long_text else "ERROR [REDACTED] [REDACTED] [REDACTED]"
                )
                for secret in configured_secrets:
                    assert secret not in result.model_dump_json()
        stderr = capsys.readouterr().err
        assert "diagnostic" not in stderr
        assert "x" * 50 not in stderr
        for secret in configured_secrets:
            assert secret not in stderr
    finally:
        configure_tool_logging(False)


async def test_broker_cancellation_propagates_without_retry(config: ServerConfig) -> None:
    from etrade_mcp.inputs import PlacementRequest
    from etrade_mcp.policy import ToolPolicy
    from etrade_mcp.server import Runtime, invoke
    from etrade_mcp.tools import mutation_tools

    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        raise asyncio.CancelledError

    settings = configured(config)
    policy = ToolPolicy(settings.server, {tool.name: tool.capability for tool in mutation_tools()})
    async with broker_factory(handler)(config.broker, "default") as client:
        state = Runtime(settings, policy, client)
        with pytest.raises(asyncio.CancelledError):
            await invoke(
                "orders_place",
                state,
                lambda: client.orders.place("synthetic-key", PlacementRequest.model_validate(BODY)),
            )
    assert len(seen) == 1
