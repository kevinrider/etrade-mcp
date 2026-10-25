"""Test-only server with real client services and synthetic broker responses."""

import argparse
import json
from collections import Counter

import httpx
from etrade_python import ETradeClient, ETradeSettings, PreviewOrderRequest

from etrade_mcp.config import ServerConfig, ServerSettings
from etrade_mcp.server import EmptyInput, ToolSpec, create_server, server_status
from etrade_mcp.tools import preview_tools, read_tools
from tests.preview_cases import PREVIEW_RESPONSE, REQUESTS
from tests.read_cases import CASES
from tests.specialized_cases import CASES as SPECIALIZED_CASES
from tests.test_reads import broker_factory
from tests.test_server import mutation_probe


def broker_response(request: httpx.Request) -> httpx.Response:
    if request.url.path.endswith("/preview.json"):
        account = request.url.path.split("/")[3]
        suffix = request.url.path.split("/orders/")[1]
        assert (request.method, suffix) in {
            ("POST", "preview.json"),
            ("PUT", "17/change/preview.json"),
        }
        assert json.loads(request.content) in [
            PreviewOrderRequest.model_validate(value).request_body() for value in REQUESTS.values()
        ] + [
            {"PreviewOrderRequest": case["canonical_preview_request"]}
            for cases in SPECIALIZED_CASES.values()
            for case in cases
        ]
        if account == "preview-timeout":
            raise httpx.ReadTimeout("fake-private-timeout", request=request)
        if account == "preview-broken":
            return httpx.Response(200, json={"unrecognized": "fake-private-broker-detail"})
        if account == "preview-empty":
            return httpx.Response(200, json={"PreviewOrderResponse": {"PreviewIds": []}})
        if account == "preview-bad-id":
            return httpx.Response(
                200, json={"PreviewOrderResponse": {"PreviewIds": [{"previewId": True}]}}
            )
        statuses = {
            "preview-reject": 400,
            "preview-auth": 401,
            "preview-rate": 429,
            "preview-down": 503,
        }
        if account in statuses:
            return httpx.Response(
                statuses[account],
                headers={"Retry-After": "0"},
                json={"Error": {"code": "100", "message": "fake-private-broker-detail"}},
            )
        assert account == "synthetic-key"
        return httpx.Response(200, json=PREVIEW_RESPONSE)
    if request.url.path == "/v1/market/quote/REJECT.json":
        return httpx.Response(
            400, json={"Error": {"code": "100", "message": "fake-private-broker-detail"}}
        )
    if request.url.path == "/v1/market/quote/BROKEN.json":
        return httpx.Response(200, json={"unrecognized": "fake-private-broker-detail"})
    for case in CASES:
        if request.url.path == case.path:
            return httpx.Response(200, json=case.payload)
    raise AssertionError("Unexpected mocked broker request")


def client_factory(settings: ETradeSettings, profile: str) -> ETradeClient:
    failures: Counter[str] = Counter()

    def response(request: httpx.Request) -> httpx.Response:
        if "/accounts/preview-" in request.url.path:
            failures[request.url.path] += 1
            assert failures[request.url.path] == 1, "Preview failure was retried"
        return broker_response(request)

    return broker_factory(response)(settings, profile)


def tool_specs() -> list[ToolSpec]:
    return [
        ToolSpec("server_status", server_status, EmptyInput),
        *read_tools(),
        *preview_tools(),
        ToolSpec("mutation_probe", mutation_probe, EmptyInput, "order_execution"),
    ]


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--tool-allowlist")
    options = parser.parse_args()
    config = ServerConfig(
        server=ServerSettings(transport="stdio", tool_allowlist=options.tool_allowlist),
        broker=ETradeSettings(
            environment="sandbox", consumer_key="fake-key", consumer_secret="fake-secret"
        ),
    )
    create_server(config, client_factory=client_factory, tools=tool_specs()).run(transport="stdio")
