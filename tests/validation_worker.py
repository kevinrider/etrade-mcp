"""Offline worker: invalid arguments must never dispatch a broker HTTP request."""

import logging

import httpx
from etrade_python import ETradeSettings

from etrade_mcp.config import ServerConfig, ServerSettings
from etrade_mcp.server import ToolSpec, create_server
from etrade_mcp.tools import preview_tools, read_tools
from tests.test_reads import broker_factory
from tests.validation_cases import CASES


def validation_tools() -> list[ToolSpec]:
    names = {case.tool for case in CASES}
    return [tool for tool in [*read_tools(), *preview_tools()] if tool.name in names]


def forbidden(request: httpx.Request) -> httpx.Response:
    raise AssertionError("Invalid arguments dispatched a broker request")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    create_server(
        ServerConfig(
            server=ServerSettings(transport="stdio"),
            broker=ETradeSettings(consumer_key="fake-key", consumer_secret="fake-broker-secret"),
        ),
        tools=validation_tools(),
        client_factory=broker_factory(forbidden),
    ).run(transport="stdio")
