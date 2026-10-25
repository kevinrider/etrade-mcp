"""Offline stdio worker: actual client preview methods and synthetic broker errors."""

import logging
from collections import Counter

import httpx
from etrade_python import ETradeClient, ETradeSettings

from etrade_mcp.config import ServerConfig, ServerSettings
from etrade_mcp.server import ClientFactory, ToolSpec, create_server
from etrade_mcp.tools import preview_tools
from tests.broker_error_cases import CASES
from tests.test_reads import broker_factory

TOOLS = {"orders_preview", "orders_preview_change", "orders_preview_equity"}


def diagnostic_tools() -> list[ToolSpec]:
    return [spec for spec in preview_tools() if spec.name in TOOLS]


def diagnostic_factory(calls: list[httpx.Request] | None = None) -> ClientFactory:
    def factory(settings: ETradeSettings, profile: str) -> ETradeClient:
        counts: Counter[str] = Counter()

        def response(request: httpx.Request) -> httpx.Response:
            if calls is not None:
                calls.append(request)
            assert request.method in {"POST", "PUT"}
            assert request.url.path.endswith("/preview.json")
            counts[request.url.path] += 1
            assert counts[request.url.path] == 1, "A diagnostic request was retried"
            account = request.url.path.split("/")[3]
            case_name = account.removeprefix("diagnostic-").rsplit("-", 1)[0]
            case = next(case for case in CASES if case.name == case_name)
            return case.response(settings)

        return broker_factory(response)(settings, profile)

    return factory


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    config = ServerConfig(
        server=ServerSettings(transport="stdio"),
        broker=ETradeSettings(consumer_key="fake-key", consumer_secret="fake-broker-secret"),
    )
    create_server(config, tools=diagnostic_tools(), client_factory=diagnostic_factory()).run(
        transport="stdio"
    )
