"""Public alerts read tools; query and response handling remain in etrade-python."""

from typing import Any

from etrade_python import AlertDetailsResponse, AlertsResponse
from mcp.server.mcpserver.context import Context
from pydantic import Field

from etrade_mcp.inputs import AlertListRequest, AlertRequest
from etrade_mcp.responses import Response, WireModel
from etrade_mcp.server import Runtime, invoke


class AlertsListInput(WireModel):
    request: AlertListRequest | None = None


async def alerts_list(
    ctx: Context[Runtime, Any], request: AlertListRequest | None = None
) -> Response[AlertsResponse]:
    """Read alerts with supported category, status, search, count, and direction filters."""
    state = ctx.request_context.lifespan_context
    return await invoke("alerts_list", state, lambda: state.client.alerts.list(request))


class AlertsGetInput(WireModel):
    alert_id: int = Field(ge=1, strict=True)
    request: AlertRequest | None = None


async def alerts_get(
    ctx: Context[Runtime, Any], alert_id: int, request: AlertRequest | None = None
) -> Response[AlertDetailsResponse]:
    """Read an alert by ID, with optional HTML-tag inclusion. Does not delete alerts."""
    state = ctx.request_context.lifespan_context
    return await invoke("alerts_get", state, lambda: state.client.alerts.get(alert_id, request))
