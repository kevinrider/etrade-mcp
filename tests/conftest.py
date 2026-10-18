import os
import socket
from pathlib import Path
from typing import Any

import httpx
import pytest
from etrade_python import ETradeClient, ETradeSettings, MemoryCredentialStore

from etrade_mcp.config import ServerConfig, ServerSettings


@pytest.fixture(autouse=True)
def isolated_environment(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    for name in list(os.environ):
        if name.startswith("ETRADE_"):
            monkeypatch.delenv(name)
    monkeypatch.setenv("PYTHON_KEYRING_BACKEND", "keyring.backends.null.Keyring")
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "cache"))


@pytest.fixture(autouse=True)
def no_external_network(monkeypatch: pytest.MonkeyPatch) -> None:
    lookup = socket.getaddrinfo

    def guarded_lookup(host: Any, *args: Any, **kwargs: Any) -> Any:
        if host not in {"127.0.0.1", "::1", "localhost", b"127.0.0.1", b"::1", b"localhost"}:
            raise AssertionError("External network forbidden in offline tests")
        return lookup(host, *args, **kwargs)

    async def forbidden(self: httpx.AsyncHTTPTransport, request: httpx.Request) -> httpx.Response:
        raise AssertionError("Broker HTTP must use MockTransport")

    monkeypatch.setattr(socket, "getaddrinfo", guarded_lookup)
    monkeypatch.setattr(httpx.AsyncHTTPTransport, "handle_async_request", forbidden)


@pytest.fixture
def broker() -> ETradeSettings:
    return ETradeSettings(consumer_key="fake-key", consumer_secret="fake-broker-secret")


@pytest.fixture
def config(broker: ETradeSettings) -> ServerConfig:
    return ServerConfig(server=ServerSettings(transport="stdio"), broker=broker)


def memory_client(settings: ETradeSettings, profile: str) -> ETradeClient:
    return ETradeClient(settings, profile=profile, credential_store=MemoryCredentialStore())
