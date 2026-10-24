"""Public order reads and previews; brokerage behavior stays in etrade-python."""

from typing import Annotated, Any

from etrade_python import OrdersResponse, PreviewOrderResponse
from mcp.server.mcpserver.context import Context
from mcp.types import CallToolResult
from pydantic import Field

from etrade_mcp.inputs import OrderListRequest, PreviewRequest
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


class OrdersPreviewInput(WireModel):
    account_id_key: str = Field(min_length=1)
    request: PreviewRequest


async def orders_preview(
    ctx: Context[Runtime, Any], account_id_key: str, request: PreviewRequest
) -> Annotated[CallToolResult, Response[PreviewOrderResponse]]:
    """Preview a complete new order, including multiple entries and legs. Does not submit it.
    Use decimal strings for modeled prices/quantities. The host owns preview/request
    association, freshness, review, and human approval. No approval is attested or stored.
    """
    state = ctx.request_context.lifespan_context
    return await invoke(
        "orders_preview", state, lambda: state.client.orders.preview(account_id_key, request)
    )


class OrdersPreviewChangeInput(OrdersPreviewInput):
    order_id: int = Field(gt=0, strict=True)


async def orders_preview_change(
    ctx: Context[Runtime, Any], account_id_key: str, order_id: int, request: PreviewRequest
) -> Annotated[CallToolResult, Response[PreviewOrderResponse]]:
    """Preview a complete replacement for the explicitly targeted account/order. Does not
    modify the order. Request and approval association belongs to the host; material
    changes require renewed host review. Uses decimal strings for modeled prices/quantities.
    """
    state = ctx.request_context.lifespan_context
    return await invoke(
        "orders_preview_change",
        state,
        lambda: state.client.orders.preview_change(account_id_key, order_id, request),
    )
