"""Test-only process with real client APIs and a recording mock broker transport."""

import argparse
import asyncio
import json
from pathlib import Path

import httpx
import uvicorn
from etrade_python import ETradeSettings

from etrade_mcp.config import ServerConfig, ServerSettings
from etrade_mcp.http import create_http_app
from etrade_mcp.server import create_server
from etrade_mcp.tool_logging import configure_tool_logging
from tests.audit_cases import page_response, read_response, wait_until
from tests.mutation_cases import response
from tests.test_reads import broker_factory


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--record-path", type=Path, required=True)
    parser.add_argument("--release-path", type=Path)
    parser.add_argument("--scenario", choices=["reads", "pages", "lifecycle"], default="reads")
    args = parser.parse_args()
    record: Path = args.record_path
    release: Path | None = args.release_path

    def event(value: dict[str, object]) -> None:
        with record.open("a") as stream:
            stream.write(json.dumps(value) + "\n")

    async def handler(request: httpx.Request) -> httpx.Response:
        event(
            {
                "method": request.method,
                "path": request.url.path,
                "params": dict(request.url.params),
                "body": json.loads(request.content) if request.content else None,
            }
        )
        if args.scenario == "reads":
            return read_response(request)
        if args.scenario == "pages":
            return page_response(request)
        if request.method != "GET":
            assert release is not None
            # The synthetic broker has received the mutation. Keep its reply
            # pending so the parent can deliberately lose the transport/process.
            await asyncio.to_thread(wait_until, release.exists)
            result = response(request)
            event({"completed": True})
            return result
        if request.url.path == "/v1/user/alerts.json":
            return httpx.Response(200, json={"AlertsResponse": {"totalAlerts": 0, "Alert": []}})
        assert request.url.path.endswith("/orders.json")
        return httpx.Response(200, json={"OrdersResponse": {"Order": [{"orderId": 701}]}})

    settings = ServerSettings()
    configure_tool_logging(settings.debug_tool_calls)
    config = ServerConfig(
        server=settings,
        broker=ETradeSettings(consumer_key="fake-key", consumer_secret="fake-broker-secret"),
    )
    server = create_server(config, client_factory=broker_factory(handler))
    if settings.transport == "stdio":
        server.run(transport="stdio")
    else:
        uvicorn.run(
            create_http_app(server, settings),
            host=settings.bind_host,
            port=settings.bind_port,
            log_config=None,
            access_log=False,
            proxy_headers=False,
        )


if __name__ == "__main__":
    main()
