"""Test-only server with real client services and synthetic broker responses."""

import httpx
from etrade_python import ETradeSettings

from etrade_mcp.config import ServerConfig, ServerSettings
from etrade_mcp.server import EmptyInput, ToolSpec, create_server, server_status
from etrade_mcp.tools import read_tools
from tests.read_cases import CASES
from tests.test_reads import broker_factory
from tests.test_server import mutation_probe


def broker_response(request: httpx.Request) -> httpx.Response:
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


client_factory = broker_factory(broker_response)


def tool_specs() -> list[ToolSpec]:
    return [
        ToolSpec("server_status", server_status, EmptyInput),
        *read_tools(),
        ToolSpec("mutation_probe", mutation_probe, EmptyInput, "order_execution"),
    ]


if __name__ == "__main__":
    config = ServerConfig(
        server=ServerSettings(transport="stdio"),
        broker=ETradeSettings(
            environment="sandbox", consumer_key="fake-key", consumer_secret="fake-secret"
        ),
    )
    create_server(config, client_factory=client_factory, tools=tool_specs()).run(transport="stdio")
