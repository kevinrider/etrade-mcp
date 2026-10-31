"""Test-only stdio server: real client services over a recording mock transport."""

import argparse
import json
from pathlib import Path

import httpx
from etrade_python import ETradeSettings

from etrade_mcp.config import ServerConfig, ServerSettings
from etrade_mcp.server import create_server
from etrade_mcp.tool_logging import configure_tool_logging
from tests.mutation_cases import response
from tests.test_reads import broker_factory


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--record-path", type=Path, required=True)
    args = parser.parse_args()
    record_path: Path = args.record_path

    def handler(request: httpx.Request) -> httpx.Response:
        with record_path.open("a") as stream:
            stream.write(
                json.dumps(
                    {
                        "method": request.method,
                        "path": request.url.path,
                        "body": json.loads(request.content) if request.content else None,
                    }
                )
                + "\n"
            )
        return response(request)

    settings = ServerSettings(transport="stdio")
    configure_tool_logging(settings.debug_tool_calls)
    create_server(
        ServerConfig(
            server=settings,
            broker=ETradeSettings(consumer_key="fake-key", consumer_secret="fake-broker-secret"),
        ),
        client_factory=broker_factory(handler),
    ).run(transport="stdio")


if __name__ == "__main__":
    main()
