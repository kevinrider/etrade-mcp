"""Startup policy, applied independently to registration and invocation."""

from collections.abc import Mapping
from typing import Literal

from etrade_mcp.config import ConfigurationError, ServerSettings
from etrade_mcp.responses import Failure

Capability = Literal["read", "order_execution", "alert_deletion"]


class ToolPolicy:
    def __init__(self, settings: ServerSettings, capabilities: Mapping[str, Capability]) -> None:
        self.settings = settings
        self.capabilities = dict(capabilities)
        allowlist = settings.allowed_tools
        if allowlist is not None and allowlist.difference(self.capabilities):
            raise ConfigurationError("Tool allowlist contains an unknown tool name")

    def denial(self, name: str) -> Failure | None:
        capability = self.capabilities.get(name)
        allowlist = self.settings.allowed_tools
        if capability is None or allowlist is not None and name not in allowlist:
            return Failure(code="tool_not_available", message="Tool is not available.")
        if capability == "order_execution" and not self.settings.enable_order_execution:
            return Failure(code="execution_disabled", message="Order execution is disabled.")
        if capability == "alert_deletion" and not self.settings.enable_alert_deletion:
            return Failure(code="execution_disabled", message="Alert deletion is disabled.")
        return None

    @property
    def exposed(self) -> list[str]:
        return sorted(name for name in self.capabilities if self.denial(name) is None)
