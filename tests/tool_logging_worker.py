"""Test-only server: real client preview calls use a fake broker transport."""

import httpx
from etrade_python import ETradeSettings

from etrade_mcp.config import ServerConfig, ServerSettings
from etrade_mcp.server import ToolSpec, create_server
from etrade_mcp.tool_logging import configure_tool_logging
from etrade_mcp.tools import preview_tools
from tests.preview_cases import PREVIEW_RESPONSE
from tests.test_reads import broker_factory

RESPONSE_ONLY = "broker-response-only-text"


def logging_tools() -> list[ToolSpec]:
    return [spec for spec in preview_tools() if spec.name == "orders_preview_equity"]


def response(request: httpx.Request) -> httpx.Response:
    assert request.method == "POST" and request.url.path.endswith("/orders/preview.json")
    if "/reject-account/" in request.url.path:
        return httpx.Response(400, json={"Error": {"code": "51016", "message": RESPONSE_ONLY}})
    return httpx.Response(200, json=PREVIEW_RESPONSE)


if __name__ == "__main__":
    settings = ServerSettings(transport="stdio")
    configure_tool_logging(settings.debug_tool_calls)
    create_server(
        ServerConfig(
            server=settings,
            broker=ETradeSettings(consumer_key="fake-key", consumer_secret="fake-broker-secret"),
        ),
        tools=logging_tools(),
        client_factory=broker_factory(response),
    ).run(transport="stdio")
