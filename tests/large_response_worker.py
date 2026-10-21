"""Test-only stdio server using a real client with synthetic broker HTTP responses."""

import httpx
from etrade_python import ETradeClient, ETradeSettings, MemoryCredentialStore

from etrade_mcp.config import ServerConfig, ServerSettings
from etrade_mcp.server import create_server
from tests.large_response_data import CHAIN_DATA


class FakeAuth:
    async def authenticate(self, request: httpx.Request) -> None:
        request.headers["Authorization"] = "OAuth fake-test-authorization"


def client_factory(settings: ETradeSettings, profile: str) -> ETradeClient:
    calls = 0

    def response(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        assert calls == 1
        assert request.method == "GET"
        assert request.url.path == "/v1/market/optionchains.json"
        assert request.url.params == httpx.QueryParams({"symbol": "SYN"})
        return httpx.Response(200, json={"OptionChainResponse": CHAIN_DATA})

    return ETradeClient(
        settings,
        profile=profile,
        authenticator=FakeAuth(),
        credential_store=MemoryCredentialStore(),
        http_transport=httpx.MockTransport(response),
    )


if __name__ == "__main__":
    config = ServerConfig(
        server=ServerSettings(transport="stdio"),
        broker=ETradeSettings(
            environment="sandbox", consumer_key="fake-key", consumer_secret="fake-secret"
        ),
    )
    create_server(config, client_factory=client_factory).run(transport="stdio")
