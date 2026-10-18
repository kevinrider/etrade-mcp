"""One public client lifespan and one tool registry for both transports."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncGenerator, Awaitable, Callable, Sequence
from contextlib import asynccontextmanager
from dataclasses import dataclass
from importlib.metadata import version
from typing import Any, TypeVar, cast

from etrade_python import ETradeClient, ETradeSettings
from mcp.server import MCPServer
from mcp.server.context import CallNext, HandlerResult, ServerRequestContext
from mcp.server.mcpserver.context import Context
from mcp.types import CallToolResult, ToolAnnotations
from mcp.types import Tool as MCPTool
from pydantic import BaseModel, ValidationError

from etrade_mcp._version import __version__
from etrade_mcp.config import CacheLimits, ServerConfig
from etrade_mcp.policy import Capability, ToolPolicy
from etrade_mcp.responses import (
    Failure,
    Response,
    WireModel,
    classified_error,
    error_result,
    metadata,
)

ClientFactory = Callable[[ETradeSettings, str], ETradeClient]
T = TypeVar("T", bound=BaseModel)


@dataclass(frozen=True)
class Runtime:
    config: ServerConfig
    policy: ToolPolicy
    client: ETradeClient


@dataclass(frozen=True)
class ToolSpec:
    name: str
    function: Callable[..., Awaitable[Any]]
    input_model: type[BaseModel]
    capability: Capability = "read"


class AdapterServer(MCPServer[Runtime]):
    """Advertise the same strict schemas that the validation boundary enforces."""

    def __init__(self, inputs: dict[str, type[BaseModel]], **kwargs: Any) -> None:
        self.inputs = inputs
        super().__init__(**kwargs)

    async def list_tools(self) -> list[MCPTool]:
        tools = await super().list_tools()
        return [
            tool.model_copy(update={"input_schema": self.inputs[tool.name].model_json_schema()})
            for tool in tools
        ]


class EmptyInput(WireModel):
    pass


class Status(WireModel):
    server_version: str
    client_version: str
    mcp_sdk_version: str
    transport: str
    enabled_tools: list[str]
    order_execution_enabled: bool
    alert_deletion_enabled: bool
    credential_status: str
    credential_status_source: str = "local_estimate"
    result_cache_implemented: bool = False
    result_cache_limits: CacheLimits


async def invoke(name: str, state: Runtime, operation: Callable[[], Awaitable[T]]) -> Response[T]:
    """Handler-side policy plus a sanitized error boundary. Never retries calls."""
    denied = state.policy.denial(name)
    if denied is not None:
        return Response[T](ok=False, error=denied, meta=metadata(state.config))
    mutation = state.policy.capabilities[name] != "read"
    try:
        data = await operation()
    except asyncio.CancelledError:
        # Let MCP cancellation/shutdown propagate. A lost response cannot certify
        # whether a future mutation was submitted; the host owns reconciliation.
        raise
    except Exception as error:
        token = state.config.server.http_bearer_token
        return Response[T](
            ok=False,
            error=classified_error(
                error,
                mutation=mutation,
                secrets=(
                    state.config.broker.consumer_key.get_secret_value(),
                    state.config.broker.consumer_secret.get_secret_value(),
                    token.get_secret_value() if token is not None else "",
                ),
            ),
            meta=metadata(state.config),
        )
    return Response[T](ok=True, data=data, meta=metadata(state.config))


async def server_status(ctx: Context[Runtime, Any]) -> Response[Status]:
    """Report server policy and a local credential estimate; makes no broker request."""
    state = ctx.request_context.lifespan_context

    async def read_status() -> Status:
        credentials = await state.client.session.load()
        return Status(
            server_version=__version__,
            client_version=version("etrade-python"),
            mcp_sdk_version=version("mcp"),
            transport=state.config.server.transport,
            enabled_tools=state.policy.exposed,
            order_execution_enabled=state.config.server.enable_order_execution,
            alert_deletion_enabled=state.config.server.enable_alert_deletion,
            credential_status=state.client.session.status(credentials).value,
            result_cache_limits=state.config.server.cache_limits,
        )

    return await invoke("server_status", state, read_status)


class ToolBoundary:
    def __init__(self, config: ServerConfig, policy: ToolPolicy, tools: Sequence[ToolSpec]) -> None:
        self.config = config
        self.policy = policy
        self.inputs = {spec.name: spec.input_model for spec in tools}

    async def __call__(
        self, ctx: ServerRequestContext[Runtime, Any], call_next: CallNext
    ) -> HandlerResult:
        if ctx.method != "tools/call":
            return await call_next(ctx)
        params = ctx.params or {}
        name = params.get("name")
        if not isinstance(name, str):
            return error_result(
                self.config, Failure(code="invalid_input", message="Tool name is required.")
            )
        denied = self.policy.denial(name)
        if denied is not None:
            return error_result(self.config, denied)
        try:
            arguments = params.get("arguments", {})
            self.inputs[name].model_validate(arguments)
        except ValidationError:
            return error_result(
                self.config, Failure(code="invalid_input", message="Tool arguments are invalid.")
            )
        # Handler invoke() catches errors before the SDK can log their contents.
        result = await call_next(ctx)
        if isinstance(result, CallToolResult):
            data = result.structured_content
            if isinstance(data, dict) and cast(dict[str, object], data).get("ok") is False:
                return result.model_copy(update={"is_error": True})
        elif isinstance(result, dict):
            tool_result = CallToolResult.model_validate(result)
            data = tool_result.structured_content
            if isinstance(data, dict) and cast(dict[str, object], data).get("ok") is False:
                return tool_result.model_copy(update={"is_error": True})
        return result


def default_client(settings: ETradeSettings, profile: str) -> ETradeClient:
    return ETradeClient(settings, profile=profile)


def create_server(
    config: ServerConfig,
    *,
    client_factory: ClientFactory = default_client,
    tools: Sequence[ToolSpec] | None = None,
) -> MCPServer[Runtime]:
    """Build the same server for either transport; injection is for library tests."""
    specs = (
        list(tools) if tools is not None else [ToolSpec("server_status", server_status, EmptyInput)]
    )
    if len({spec.name for spec in specs}) != len(specs):
        from etrade_mcp.config import ConfigurationError

        raise ConfigurationError("Duplicate tool name")
    policy = ToolPolicy(config.server, {spec.name: spec.capability for spec in specs})

    @asynccontextmanager
    async def lifespan(server: MCPServer[Runtime]) -> AsyncGenerator[Runtime]:
        async with client_factory(config.broker, config.server.profile) as client:
            yield Runtime(config, policy, client)

    server = AdapterServer(
        inputs={spec.name: spec.input_model for spec in specs},
        name="etrade-mcp",
        version=__version__,
        instructions=(
            "The host owns human approval, preview/request binding, submission history, "
            "duplicate prevention and reconciliation. No server approval attestation is provided."
        ),
        lifespan=lifespan,
        subscriptions=False,
        middleware=[ToolBoundary(config, policy, specs)],
    )
    for spec in specs:
        if policy.denial(spec.name) is None:
            server.tool(
                name=spec.name,
                annotations=ToolAnnotations(
                    read_only_hint=spec.capability == "read",
                    destructive_hint=spec.capability != "read",
                    idempotent_hint=spec.name == "server_status",
                    open_world_hint=spec.name != "server_status",
                ),
            )(spec.function)
    return server
