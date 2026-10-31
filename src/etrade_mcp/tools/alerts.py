"""Public alerts read tools; query and response handling remain in etrade-python."""

from typing import Annotated, Any

from etrade_python import AlertDetailsResponse, AlertsResponse, DeleteAlertsResponse
from mcp.server.mcpserver.context import Context
from mcp.types import CallToolResult
from pydantic import Field

from etrade_mcp.inputs import AlertListRequest, AlertRequest
from etrade_mcp.responses import Failure, Response, WireModel
from etrade_mcp.server import Runtime, invoke


class AlertsListInput(WireModel):
    request: AlertListRequest | None = None


async def alerts_list(
    ctx: Context[Runtime, Any], request: AlertListRequest | None = None
) -> Annotated[CallToolResult, Response[AlertsResponse]]:
    """Read alerts with supported category, status, search, count, and direction filters."""
    state = ctx.request_context.lifespan_context
    return await invoke("alerts_list", state, lambda: state.client.alerts.list(request))


class AlertsGetInput(WireModel):
    alert_id: int = Field(ge=1, strict=True)
    request: AlertRequest | None = None


async def alerts_get(
    ctx: Context[Runtime, Any], alert_id: int, request: AlertRequest | None = None
) -> Annotated[CallToolResult, Response[AlertDetailsResponse]]:
    """Read an alert by ID, with optional HTML-tag inclusion. Does not delete alerts."""
    state = ctx.request_context.lifespan_context
    return await invoke("alerts_get", state, lambda: state.client.alerts.get(alert_id, request))


class AlertsDeleteInput(WireModel):
    alert_ids: list[Annotated[int, Field(gt=0, strict=True)]] = Field(min_length=1)


def deletion_failure(result: DeleteAlertsResponse) -> Failure | None:
    status = (result.result or "").strip().upper()
    failed = result.failed_alerts is not None and bool(result.failed_alerts.alert_ids)
    if failed or status == "ERROR":
        return Failure(
            code="broker_rejection",
            message=(
                "Broker reported alert deletion failures. "
                "Inspect the result and reconcile before resubmitting."
            ),
            alert_deletion_result=result,
        )
    if status != "SUCCESS":
        return Failure(
            code="uncertain_execution",
            message="Alert deletion outcome is unclear. Reconcile before resubmitting.",
            alert_deletion_result=result,
        )
    return None


async def alerts_delete(
    ctx: Context[Runtime, Any], alert_ids: list[Annotated[int, Field(gt=0, strict=True)]]
) -> Annotated[CallToolResult, Response[DeleteAlertsResponse]]:
    """Delete the supplied alert IDs once; preserve failed IDs without retrying the batch."""
    state = ctx.request_context.lifespan_context
    return await invoke(
        "alerts_delete",
        state,
        lambda: state.client.alerts.delete(alert_ids),
        result_error=deletion_failure,
    )
