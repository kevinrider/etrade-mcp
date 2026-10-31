from __future__ import annotations

import asyncio
import socket
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import Any

import httpx2
import uvicorn
from etrade_python import ETradeSettings
from mcp.client.streamable_http import streamable_http_client
from mcp.server import MCPServer
from pydantic import SecretStr

from etrade_mcp.config import ServerConfig, ServerSettings
from etrade_mcp.http import create_http_app
from etrade_mcp.server import ClientFactory, Runtime, ToolSpec, create_server
from tests.conftest import memory_client

TOKEN = "fake-http-bearer-secret"

READ_TOOLS = {
    "server_status",
    "accounts_list",
    "accounts_get_balance",
    "portfolio_get_positions",
    "transactions_list",
    "transactions_get",
    "market_get_quote",
    "market_get_quotes",
    "market_lookup_product",
    "market_get_option_expirations",
    "market_get_option_chain",
    "orders_list",
    "alerts_list",
    "alerts_get",
}
PREVIEW_TOOLS = {"orders_preview", "orders_preview_change"}
ORDER_FAMILIES = (
    "equity",
    "single_option",
    "buy_write",
    "vertical",
    "butterfly",
    "condor",
    "iron_butterfly",
    "iron_condor",
    "call_spread_short_put",
)
SPECIALIZED_TOOLS = {
    f"orders_preview_{prefix}{family}" for family in ORDER_FAMILIES for prefix in ("", "change_")
}
DEFAULT_TOOLS = READ_TOOLS | PREVIEW_TOOLS | SPECIALIZED_TOOLS
ORDER_MUTATIONS = {"orders_place", "orders_place_change", "orders_cancel"}
MUTATION_TOOLS = ORDER_MUTATIONS | {"alerts_delete"}
ALL_TOOLS = DEFAULT_TOOLS | MUTATION_TOOLS


@asynccontextmanager
async def http_server(
    broker: ETradeSettings,
    *,
    tools: list[ToolSpec] | None = None,
    client_factory: ClientFactory = memory_client,
    **settings: Any,
) -> AsyncGenerator[tuple[str, MCPServer[Runtime]]]:
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    sock.listen()
    port = int(sock.getsockname()[1])
    config = ServerConfig(
        server=ServerSettings(
            transport="streamable-http", port=port, http_bearer_token=SecretStr(TOKEN), **settings
        ),
        broker=broker,
    )
    app = create_server(config, client_factory=client_factory, tools=tools)
    runner = uvicorn.Server(
        uvicorn.Config(
            create_http_app(app, config.server),
            log_config=None,
            lifespan="on",
            access_log=False,
            proxy_headers=False,
        )
    )
    task = asyncio.create_task(runner.serve(sockets=[sock]))
    try:
        async with asyncio.timeout(5):
            while not runner.started:
                if task.done():
                    await task
                await asyncio.sleep(0.01)
        yield f"http://127.0.0.1:{port}/mcp", app
    finally:
        runner.should_exit = True
        await asyncio.wait_for(task, 5)
        sock.close()


@asynccontextmanager
async def authenticated_http(url: str) -> AsyncGenerator[tuple[Any, Any]]:
    async with httpx2.AsyncClient(
        headers={"Authorization": f"Bearer {TOKEN}"}, trust_env=False
    ) as http:
        async with streamable_http_client(url, http_client=http) as streams:
            yield streams[0], streams[1]
