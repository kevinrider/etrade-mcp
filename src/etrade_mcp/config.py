"""Startup-only policy and configuration. Broker settings stay in etrade-python."""

from __future__ import annotations

from ipaddress import ip_address
from typing import Literal

from etrade_python import ETradeSettings
from pydantic import BaseModel, ConfigDict, Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class ConfigurationError(Exception):
    """Sanitized startup failure; never include setting values."""


class ServerSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="ETRADE_MCP_",
        env_file=None,
        extra="forbid",
        frozen=True,
        hide_input_in_errors=True,
    )

    transport: Literal["streamable-http", "stdio"] = "streamable-http"
    profile: str = "default"
    host: str | None = None
    port: int | None = Field(default=None, ge=1, le=65535)
    http_bearer_token: SecretStr | None = Field(default=None, repr=False)
    enable_order_execution: bool = False
    enable_alert_deletion: bool = False
    # A string preserves the difference between omitted and explicitly empty.
    tool_allowlist: str | None = None

    @field_validator("profile")
    @classmethod
    def valid_profile(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Profile cannot be blank")
        return value

    @model_validator(mode="after")
    def transport_configuration(self) -> ServerSettings:
        if self.transport == "stdio":
            if self.host is not None or self.port is not None or self.http_bearer_token is not None:
                raise ValueError("HTTP-only settings are not accepted for stdio")
        else:
            try:
                loopback = ip_address(self.bind_host).is_loopback
            except ValueError:
                loopback = False
            if not loopback:
                raise ValueError("HTTP binding requires a loopback IP literal")
            token = self.http_bearer_token
            if token is None or not token.get_secret_value():
                raise ValueError("HTTP bearer token is required")
            raw = token.get_secret_value()
            if not raw.isascii() or any(ord(c) <= 32 or ord(c) >= 127 for c in raw):
                raise ValueError("HTTP bearer token must be a nonempty header-safe token")
        _ = self.allowed_tools
        return self

    @property
    def bind_host(self) -> str:
        return self.host if self.host is not None else "127.0.0.1"

    @property
    def bind_port(self) -> int:
        return self.port if self.port is not None else 8000

    @property
    def allowed_tools(self) -> frozenset[str] | None:
        if self.tool_allowlist is None:
            return None
        if self.tool_allowlist == "":
            return frozenset()
        names = [part.strip() for part in self.tool_allowlist.split(",")]
        if any(not name or not name.replace("_", "").isalnum() for name in names):
            raise ValueError("Allowlist must contain exact tool names separated by commas")
        return frozenset(names)


class ServerConfig(BaseModel):
    model_config = ConfigDict(frozen=True, arbitrary_types_allowed=True, hide_input_in_errors=True)
    server: ServerSettings
    broker: ETradeSettings = Field(repr=False)
