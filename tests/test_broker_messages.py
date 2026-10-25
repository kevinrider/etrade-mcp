"""Broker text is explicit diagnostic data, never an exception or raw-body fallback."""

import logging
import os
import sys
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, Literal
from urllib.parse import quote, quote_plus

import httpx
import pytest
from etrade_python import ETradeApiError, ETradeSettings, ETradeUnavailableError
from mcp import Client
from mcp.client.stdio import StdioServerParameters, stdio_client

from etrade_mcp.responses import BROKER_MESSAGE_LIMIT, broker_diagnostic, classified_error
from tests.broker_error_cases import CASES, RAW_SENTINEL
from tests.broker_error_worker import TOOLS, diagnostic_factory, diagnostic_tools
from tests.helpers import TOKEN, authenticated_http, http_server
from tests.preview_cases import REQUESTS
from tests.test_reads import broker_factory
from tests.test_server import payload


@pytest.mark.parametrize(
    "text,expected",
    [
        (None, None),
        ("", None),
        (" \t\n", None),
        ("A useful broker message.", "A useful broker message."),
        ("  Vérifiez\n la date. ", "Vérifiez la date."),
        ("Z" * 1400, "Z" * 1000),
    ],
)
def test_message_normalization_and_bounds(text: str | None, expected: str | None) -> None:
    assert broker_diagnostic(text, ()) == expected


@pytest.mark.parametrize("encode", [str, quote, quote_plus])
def test_known_secret_variants_and_overlaps(encode: Any) -> None:
    secret = "adapter/credential+with spaces?"
    encoded = encode(secret)
    result = broker_diagnostic(
        f"Rejected {encoded}; another short credential. 病", (secret, "short")
    )
    assert result == "Rejected [REDACTED]; another [REDACTED] credential. 病"
    assert broker_diagnostic(
        "abc-long-secret abc-long abc", ("abc", "abc-long", "abc-long-secret")
    ) == ("[REDACTED] [REDACTED] [REDACTED]")
    assert broker_diagnostic("percent%2fsecret", ("percent/secret",)) == "[REDACTED]"
    assert broker_diagnostic("normalized multi word secret", ("multi\tword",)) == (
        "normalized [REDACTED] secret"
    )
    assert broker_diagnostic("ordinary text", ("", "  ")) == "ordinary text"


@pytest.mark.parametrize("fragment", ["f", "fake-http-", "fake-http-bearer-secre"])
def test_upstream_truncation_suppresses_partial_secrets(fragment: str) -> None:
    text = "Z" * (BROKER_MESSAGE_LIMIT - len(fragment)) + fragment
    assert broker_diagnostic(text, (TOKEN,)) is None


def test_intersecting_secrets_and_mixed_case_percent_escapes() -> None:
    assert broker_diagnostic("abcdefgh", ("abcde", "defgh")) == "[REDACTED]"
    secret = "adapter/credential+suffix?"
    encoded = "adapter%2fcredential%2Bsuffix%3f"
    assert broker_diagnostic(f"Rejected {encoded}.", (secret,)) == "Rejected [REDACTED]."
    fragment = encoded[:-4]
    upstream = "Z" * (BROKER_MESSAGE_LIMIT - len(fragment)) + fragment
    assert broker_diagnostic(upstream, (secret,)) is None


def test_redaction_precedes_adapter_truncation() -> None:
    text = "Z" * 990 + TOKEN + " End."
    result = broker_diagnostic(text, (TOKEN,))
    assert result is not None and len(result) <= BROKER_MESSAGE_LIMIT
    assert "fake-http" not in result
    upstream = "Z" * (BROKER_MESSAGE_LIMIT - len(TOKEN)) + TOKEN
    assert broker_diagnostic(upstream, (TOKEN,)) == (
        "Z" * (BROKER_MESSAGE_LIMIT - len(TOKEN)) + "[REDACTED]"
    )


def test_broker_messages_do_not_change_classification() -> None:
    error = ETradeUnavailableError(
        "fake-private-exception",
        status_code=503,
        broker_code="41002",
        broker_message="Try again later.",
    )
    failure = classified_error(error, mutation=True)
    assert failure.code == "uncertain_execution"
    assert failure.message == "Submission outcome is uncertain. Reconcile before submitting again."
    assert failure.broker_message == "Try again later."
    assert classified_error(RuntimeError("fake-private-exception")).broker_message is None
    assert classified_error(ETradeApiError("fake-private-exception")).broker_message is None


@pytest.mark.parametrize("wire", ["http", "stdio"])
@pytest.mark.parametrize("mode", ["auto", "legacy"])
async def test_real_client_diagnostics_over_mcp(
    broker: ETradeSettings,
    wire: str,
    mode: Literal["auto", "legacy"],
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.INFO)
    calls: list[httpx.Request] = []
    stderr_path = tmp_path / "server.stderr"

    async def check(client: Client) -> None:
        tools = (await client.list_tools()).tools
        assert {tool.name for tool in tools} == TOOLS
        for tool in tools:
            assert tool.output_schema is not None
            field = tool.output_schema["$defs"]["Failure"]["properties"]["broker_message"]
            assert field["default"] is None
            assert {choice["type"] for choice in field["anyOf"]} == {"string", "null"}
            assert field["anyOf"][0]["maxLength"] == 1000
        for index, name in enumerate(sorted(TOOLS)):
            for case in CASES:
                count = len(calls)
                arguments: dict[str, Any] = {
                    "account_id_key": f"diagnostic-{case.name}-{index}",
                    "request": (
                        {
                            "client_order_id": "Diagnostic1",
                            "symbol": "SYN",
                            "order_action": "BUY",
                            "quantity": "1",
                            "price_type": "MARKET",
                        }
                        if name == "orders_preview_equity"
                        else REQUESTS["equity"]
                    ),
                }
                if name == "orders_preview_change":
                    arguments["order_id"] = 17
                result = await client.call_tool(name, arguments)
                assert result.is_error
                error = payload(result)["error"]
                assert error["code"] == case.category
                assert error["status_code"] == case.status
                assert error["broker_code"] == (
                    None if case.name == "nonnumeric" else case.broker_code
                )
                assert error["broker_message"] == case.expected_message
                assert RAW_SENTINEL not in result.model_dump_json()
                await client.session.validate_tool_result(name, result)
                if wire == "http":
                    assert len(calls) == count + 1
        # Input validation has no broker diagnostic and never reaches the client.
        result = await client.call_tool("orders_preview", {"private": RAW_SENTINEL})
        assert result.is_error and payload(result)["error"]["broker_message"] is None
        assert RAW_SENTINEL not in result.model_dump_json()

    if wire == "http":
        async with http_server(
            broker, tools=diagnostic_tools(), client_factory=diagnostic_factory(calls)
        ) as (url, _):
            async with Client(authenticated_http(url), mode=mode) as client:
                await check(client)
    else:
        with stderr_path.open("w+") as stderr:

            @asynccontextmanager
            async def connection() -> AsyncGenerator[tuple[Any, Any]]:
                async with stdio_client(
                    StdioServerParameters(
                        command=sys.executable,
                        args=["-m", "tests.broker_error_worker"],
                        env=os.environ.copy(),
                    ),
                    errlog=stderr,
                ) as streams:
                    yield streams

            async with Client(connection(), mode=mode) as client:
                await check(client)
        assert RAW_SENTINEL not in stderr_path.read_text()
        for case in CASES:
            if case.expected_message:
                assert case.expected_message not in stderr_path.read_text()
    assert RAW_SENTINEL not in caplog.text
    for case in CASES:
        if case.expected_message:
            assert case.expected_message not in caplog.text


async def test_http_adapter_secret_redaction_at_client_boundary(broker: ETradeSettings) -> None:
    cases = [
        (
            f"Rejected {TOKEN} and {quote(TOKEN, safe='')}. End.",
            "Rejected [REDACTED] and [REDACTED]. End.",
        ),
        ("Z" * 990 + TOKEN, None),
    ]
    current = 0
    seen: list[httpx.Request] = []

    def response(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(400, json={"Error": {"code": "51016", "message": cases[current][0]}})

    async with http_server(
        broker, tools=diagnostic_tools(), client_factory=broker_factory(response)
    ) as (url, _):
        async with Client(authenticated_http(url)) as client:
            for index, (_, expected) in enumerate(cases):
                current = index
                result = await client.call_tool(
                    "orders_preview",
                    {"account_id_key": "synthetic-key", "request": REQUESTS["equity"]},
                )
                assert result.is_error
                assert payload(result)["error"]["broker_message"] == expected
                assert TOKEN not in result.model_dump_json()
                assert "fake-http-" not in result.model_dump_json()
                assert len(seen) == index + 1
                await client.session.validate_tool_result("orders_preview", result)
