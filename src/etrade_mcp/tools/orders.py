"""Public order reads and previews; brokerage behavior stays in etrade-python."""

from typing import Annotated, Any

from etrade_python import (
    OrdersResponse,
    PlaceOrderRequest,
    PreviewOrderRequest,
    PreviewOrderResponse,
)
from mcp.server.mcpserver.context import Context
from mcp.types import CallToolResult
from pydantic import Field, field_serializer

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


class PlacementArguments(WireModel):
    account_id_key: str = Field(min_length=1)
    request: PlaceOrderRequest

    @field_serializer("request", when_used="json")
    def canonical_request(self, value: PlaceOrderRequest) -> dict[str, Any]:
        # Advertised validation schemas retain the public request type. Serialize
        # exactly its HTTP body, preserving omission and stripping broker metadata.
        return value.request_body()["PlaceOrderRequest"]


class ChangePlacementArguments(PlacementArguments):
    order_id: int = Field(gt=0, strict=True)


class PreviewData(WireModel):
    broker_preview: PreviewOrderResponse
    placement_arguments: PlacementArguments


class ChangePreviewData(WireModel):
    broker_preview: PreviewOrderResponse
    placement_arguments: ChangePlacementArguments


async def preview_operation(
    name: str,
    state: Runtime,
    account_id_key: str,
    request: PreviewOrderRequest,
    order_id: int | None = None,
) -> CallToolResult:
    """Preview once; derive reusable arguments from the submitted body, never response legs."""

    async def operation() -> PreviewData | ChangePreviewData:
        # Snapshot precisely the public client's normalized HTTP payload before dispatch.
        body = request.request_body()["PreviewOrderRequest"]
        preview = (
            await state.client.orders.preview(account_id_key, request)
            if order_id is None
            else await state.client.orders.preview_change(account_id_key, order_id, request)
        )
        placement = PlaceOrderRequest.model_validate(
            {**body, "PreviewIds": [{"previewId": item.preview_id} for item in preview.preview_ids]}
        )
        if order_id is None:
            return PreviewData(
                broker_preview=preview,
                placement_arguments=PlacementArguments(
                    account_id_key=account_id_key, request=placement
                ),
            )
        return ChangePreviewData(
            broker_preview=preview,
            placement_arguments=ChangePlacementArguments(
                account_id_key=account_id_key, order_id=order_id, request=placement
            ),
        )

    return await invoke(name, state, operation)


class OrdersPreviewInput(WireModel):
    account_id_key: str = Field(min_length=1)
    request: PreviewRequest


async def orders_preview(
    ctx: Context[Runtime, Any], account_id_key: str, request: PreviewRequest
) -> Annotated[CallToolResult, Response[PreviewData]]:
    """Preview a complete new order, including multiple entries and legs. Does not submit it.
    Use decimal strings for modeled prices/quantities. The host owns preview/request
    association, freshness, review, and human approval. No approval is attested or stored.
    """
    state = ctx.request_context.lifespan_context
    return await preview_operation("orders_preview", state, account_id_key, request)


class OrdersPreviewChangeInput(OrdersPreviewInput):
    order_id: int = Field(gt=0, strict=True)


async def orders_preview_change(
    ctx: Context[Runtime, Any], account_id_key: str, order_id: int, request: PreviewRequest
) -> Annotated[CallToolResult, Response[ChangePreviewData]]:
    """Preview a complete replacement for the explicitly targeted account/order. Does not
    modify the order. Request and approval association belongs to the host; material
    changes require renewed host review. Uses decimal strings for modeled prices/quantities.
    """
    state = ctx.request_context.lifespan_context
    return await preview_operation(
        "orders_preview_change", state, account_id_key, request, order_id
    )
