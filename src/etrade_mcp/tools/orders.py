"""Public orders read tools; query and response handling remain in etrade-python."""

from typing import Annotated, Any

from etrade_python import OrdersResponse
from mcp.server.mcpserver.context import Context
from mcp.types import CallToolResult
from pydantic import Field

from etrade_mcp.inputs import OrderListRequest
from etrade_mcp.responses import Response, WireModel
from etrade_mcp.server import Runtime, invoke


class OrdersListInput(WireModel):
    account_id_key: str = Field(min_length=1)
    request: OrderListRequest | None = None


async def orders_list(
    ctx: Context[Runtime, Any], account_id_key: str, request: OrderListRequest | None = None
) -> Annotated[CallToolResult, Response[OrdersResponse]]:
    """Read one order page with filters and explicit continuation marker. Does not preview or
    submit orders.
    """
    state = ctx.request_context.lifespan_context
    return await invoke(
        "orders_list", state, lambda: state.client.orders.list(account_id_key, request)
    )
