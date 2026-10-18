from typing import Any

import pytest
from pydantic import SecretStr, ValidationError

from etrade_mcp.config import CacheLimits, ServerSettings


def test_defaults_and_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ETRADE_MCP_HTTP_BEARER_TOKEN", "fake-http-secret")
    settings = ServerSettings()
    assert settings.transport == "streamable-http"
    assert settings.bind_host == "127.0.0.1"
    assert settings.bind_port == 8000
    assert settings.profile == "default"
    assert settings.allowed_tools is None
    assert settings.cache_limits == CacheLimits()
    assert "fake-http-secret" not in repr(settings)
    monkeypatch.setenv("ETRADE_MCP_PROFILE", "personal")
    assert ServerSettings().profile == "personal"
    assert ServerSettings(profile="other").profile == "other"


@pytest.mark.parametrize(
    "options",
    [
        {},
        {"http_bearer_token": ""},
        {"http_bearer_token": "fake secret"},
        {"http_bearer_token": "fake-\u00e9"},
        {"http_bearer_token": "fake\nsecret"},
        {"http_bearer_token": "fake", "host": "0.0.0.0"},
        {"http_bearer_token": "fake", "host": "localhost"},
        {"http_bearer_token": "fake", "host": "192.0.2.1"},
        {"transport": "stdio", "host": "127.0.0.1"},
        {"transport": "stdio", "port": 8000},
        {"transport": "stdio", "http_bearer_token": "fake-secret"},
        {"transport": "stdio", "profile": " "},
        {"transport": "stdio", "tool_allowlist": "a,,b"},
        {"transport": "stdio", "tool_allowlist": "a-b"},
        {"transport": "stdio", "result_cache_bytes": 1024},
        {"transport": "stdio", "result_ttl_seconds": 0},
        {"transport": "stdio", "result_cache_entries": 0},
        {"transport": "stdio", "inline_result_bytes": 0},
        {"transport": "other"},
        {"http_bearer_token": "fake", "port": 0},
        {"http_bearer_token": "fake", "port": 65536},
    ],
)
def test_invalid_settings(options: dict[str, Any]) -> None:
    with pytest.raises(ValidationError) as error:
        ServerSettings(**options)
    assert "input_value" not in str(error.value)
    assert "fake-secret" not in str(error.value)


def test_allowlist_and_cache_overrides(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ETRADE_MCP_TOOL_ALLOWLIST", "server_status, other_tool")
    monkeypatch.setenv("ETRADE_MCP_RESULT_TTL_SECONDS", "60")
    settings = ServerSettings(transport="stdio")
    assert settings.allowed_tools == {"server_status", "other_tool"}
    assert settings.cache_limits.ttl_seconds == 60
    assert ServerSettings(transport="stdio", tool_allowlist="").allowed_tools == frozenset()


def test_ipv6_configuration() -> None:
    settings = ServerSettings(host="::1", http_bearer_token=SecretStr("fake"), port=9000)
    assert settings.bind_host == "::1"
    assert settings.bind_port == 9000
