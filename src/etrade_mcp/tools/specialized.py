"""Specialized preview tools; all dispatch goes through the shared preview operation."""

from typing import Annotated, Any

from mcp.server.mcpserver.context import Context
from mcp.types import CallToolResult

from etrade_mcp.order_families import (
    ButterflyRequest,
    BuyWriteRequest,
    CallSpreadShortPutRequest,
    CondorRequest,
    EquityRequest,
    IronButterflyRequest,
    IronCondorRequest,
    OrdersPreviewButterflyInput,
    OrdersPreviewBuyWriteInput,
    OrdersPreviewCallSpreadShortPutInput,
    OrdersPreviewChangeButterflyInput,
    OrdersPreviewChangeBuyWriteInput,
    OrdersPreviewChangeCallSpreadShortPutInput,
    OrdersPreviewChangeCondorInput,
    OrdersPreviewChangeEquityInput,
    OrdersPreviewChangeIronButterflyInput,
    OrdersPreviewChangeIronCondorInput,
    OrdersPreviewChangeSingleOptionInput,
    OrdersPreviewChangeVerticalInput,
    OrdersPreviewCondorInput,
    OrdersPreviewEquityInput,
    OrdersPreviewIronButterflyInput,
    OrdersPreviewIronCondorInput,
    OrdersPreviewSingleOptionInput,
    OrdersPreviewVerticalInput,
    SingleOptionRequest,
    VerticalRequest,
)
from etrade_mcp.responses import Response
from etrade_mcp.server import Runtime, ToolSpec
from etrade_mcp.tools.orders import ChangePreviewData, PreviewData, preview_operation


async def orders_preview_equity(
    ctx: Context[Runtime, Any], account_id_key: str, request: EquityRequest
) -> Annotated[CallToolResult, Response[PreviewData]]:
    """Preview the explicit equity structure without execution."""
    return await preview_operation(
        "orders_preview_equity",
        ctx.request_context.lifespan_context,
        account_id_key,
        request.to_preview(),
    )


async def orders_preview_change_equity(
    ctx: Context[Runtime, Any], account_id_key: str, order_id: int, request: EquityRequest
) -> Annotated[CallToolResult, Response[ChangePreviewData]]:
    """Preview the explicit equity structure without execution."""
    return await preview_operation(
        "orders_preview_change_equity",
        ctx.request_context.lifespan_context,
        account_id_key,
        request.to_preview(),
        order_id,
    )


async def orders_preview_single_option(
    ctx: Context[Runtime, Any], account_id_key: str, request: SingleOptionRequest
) -> Annotated[CallToolResult, Response[PreviewData]]:
    """Preview the explicit single option structure without execution."""
    return await preview_operation(
        "orders_preview_single_option",
        ctx.request_context.lifespan_context,
        account_id_key,
        request.to_preview(),
    )


async def orders_preview_change_single_option(
    ctx: Context[Runtime, Any], account_id_key: str, order_id: int, request: SingleOptionRequest
) -> Annotated[CallToolResult, Response[ChangePreviewData]]:
    """Preview the explicit single option structure without execution."""
    return await preview_operation(
        "orders_preview_change_single_option",
        ctx.request_context.lifespan_context,
        account_id_key,
        request.to_preview(),
        order_id,
    )


async def orders_preview_buy_write(
    ctx: Context[Runtime, Any], account_id_key: str, request: BuyWriteRequest
) -> Annotated[CallToolResult, Response[PreviewData]]:
    """Preview the explicit buy write structure without execution."""
    return await preview_operation(
        "orders_preview_buy_write",
        ctx.request_context.lifespan_context,
        account_id_key,
        request.to_preview(),
    )


async def orders_preview_change_buy_write(
    ctx: Context[Runtime, Any], account_id_key: str, order_id: int, request: BuyWriteRequest
) -> Annotated[CallToolResult, Response[ChangePreviewData]]:
    """Preview the explicit buy write structure without execution."""
    return await preview_operation(
        "orders_preview_change_buy_write",
        ctx.request_context.lifespan_context,
        account_id_key,
        request.to_preview(),
        order_id,
    )


async def orders_preview_vertical(
    ctx: Context[Runtime, Any], account_id_key: str, request: VerticalRequest
) -> Annotated[CallToolResult, Response[PreviewData]]:
    """Preview the explicit vertical structure without execution."""
    return await preview_operation(
        "orders_preview_vertical",
        ctx.request_context.lifespan_context,
        account_id_key,
        request.to_preview(),
    )


async def orders_preview_change_vertical(
    ctx: Context[Runtime, Any], account_id_key: str, order_id: int, request: VerticalRequest
) -> Annotated[CallToolResult, Response[ChangePreviewData]]:
    """Preview the explicit vertical structure without execution."""
    return await preview_operation(
        "orders_preview_change_vertical",
        ctx.request_context.lifespan_context,
        account_id_key,
        request.to_preview(),
        order_id,
    )


async def orders_preview_butterfly(
    ctx: Context[Runtime, Any], account_id_key: str, request: ButterflyRequest
) -> Annotated[CallToolResult, Response[PreviewData]]:
    """Preview the explicit butterfly structure without execution."""
    return await preview_operation(
        "orders_preview_butterfly",
        ctx.request_context.lifespan_context,
        account_id_key,
        request.to_preview(),
    )


async def orders_preview_change_butterfly(
    ctx: Context[Runtime, Any], account_id_key: str, order_id: int, request: ButterflyRequest
) -> Annotated[CallToolResult, Response[ChangePreviewData]]:
    """Preview the explicit butterfly structure without execution."""
    return await preview_operation(
        "orders_preview_change_butterfly",
        ctx.request_context.lifespan_context,
        account_id_key,
        request.to_preview(),
        order_id,
    )


async def orders_preview_condor(
    ctx: Context[Runtime, Any], account_id_key: str, request: CondorRequest
) -> Annotated[CallToolResult, Response[PreviewData]]:
    """Preview the explicit condor structure without execution."""
    return await preview_operation(
        "orders_preview_condor",
        ctx.request_context.lifespan_context,
        account_id_key,
        request.to_preview(),
    )


async def orders_preview_change_condor(
    ctx: Context[Runtime, Any], account_id_key: str, order_id: int, request: CondorRequest
) -> Annotated[CallToolResult, Response[ChangePreviewData]]:
    """Preview the explicit condor structure without execution."""
    return await preview_operation(
        "orders_preview_change_condor",
        ctx.request_context.lifespan_context,
        account_id_key,
        request.to_preview(),
        order_id,
    )


async def orders_preview_iron_butterfly(
    ctx: Context[Runtime, Any], account_id_key: str, request: IronButterflyRequest
) -> Annotated[CallToolResult, Response[PreviewData]]:
    """Preview the explicit iron butterfly structure without execution."""
    return await preview_operation(
        "orders_preview_iron_butterfly",
        ctx.request_context.lifespan_context,
        account_id_key,
        request.to_preview(),
    )


async def orders_preview_change_iron_butterfly(
    ctx: Context[Runtime, Any], account_id_key: str, order_id: int, request: IronButterflyRequest
) -> Annotated[CallToolResult, Response[ChangePreviewData]]:
    """Preview the explicit iron butterfly structure without execution."""
    return await preview_operation(
        "orders_preview_change_iron_butterfly",
        ctx.request_context.lifespan_context,
        account_id_key,
        request.to_preview(),
        order_id,
    )


async def orders_preview_iron_condor(
    ctx: Context[Runtime, Any], account_id_key: str, request: IronCondorRequest
) -> Annotated[CallToolResult, Response[PreviewData]]:
    """Preview the explicit iron condor structure without execution."""
    return await preview_operation(
        "orders_preview_iron_condor",
        ctx.request_context.lifespan_context,
        account_id_key,
        request.to_preview(),
    )


async def orders_preview_change_iron_condor(
    ctx: Context[Runtime, Any], account_id_key: str, order_id: int, request: IronCondorRequest
) -> Annotated[CallToolResult, Response[ChangePreviewData]]:
    """Preview the explicit iron condor structure without execution."""
    return await preview_operation(
        "orders_preview_change_iron_condor",
        ctx.request_context.lifespan_context,
        account_id_key,
        request.to_preview(),
        order_id,
    )


async def orders_preview_call_spread_short_put(
    ctx: Context[Runtime, Any], account_id_key: str, request: CallSpreadShortPutRequest
) -> Annotated[CallToolResult, Response[PreviewData]]:
    """Preview the explicit call spread short put structure without execution."""
    return await preview_operation(
        "orders_preview_call_spread_short_put",
        ctx.request_context.lifespan_context,
        account_id_key,
        request.to_preview(),
    )


async def orders_preview_change_call_spread_short_put(
    ctx: Context[Runtime, Any],
    account_id_key: str,
    order_id: int,
    request: CallSpreadShortPutRequest,
) -> Annotated[CallToolResult, Response[ChangePreviewData]]:
    """Preview the explicit call spread short put structure without execution."""
    return await preview_operation(
        "orders_preview_change_call_spread_short_put",
        ctx.request_context.lifespan_context,
        account_id_key,
        request.to_preview(),
        order_id,
    )


def specialized_preview_tools() -> list[ToolSpec]:
    return [
        ToolSpec(
            "orders_preview_equity", orders_preview_equity, OrdersPreviewEquityInput, "preview"
        ),
        ToolSpec(
            "orders_preview_change_equity",
            orders_preview_change_equity,
            OrdersPreviewChangeEquityInput,
            "preview",
        ),
        ToolSpec(
            "orders_preview_single_option",
            orders_preview_single_option,
            OrdersPreviewSingleOptionInput,
            "preview",
        ),
        ToolSpec(
            "orders_preview_change_single_option",
            orders_preview_change_single_option,
            OrdersPreviewChangeSingleOptionInput,
            "preview",
        ),
        ToolSpec(
            "orders_preview_buy_write",
            orders_preview_buy_write,
            OrdersPreviewBuyWriteInput,
            "preview",
        ),
        ToolSpec(
            "orders_preview_change_buy_write",
            orders_preview_change_buy_write,
            OrdersPreviewChangeBuyWriteInput,
            "preview",
        ),
        ToolSpec(
            "orders_preview_vertical",
            orders_preview_vertical,
            OrdersPreviewVerticalInput,
            "preview",
        ),
        ToolSpec(
            "orders_preview_change_vertical",
            orders_preview_change_vertical,
            OrdersPreviewChangeVerticalInput,
            "preview",
        ),
        ToolSpec(
            "orders_preview_butterfly",
            orders_preview_butterfly,
            OrdersPreviewButterflyInput,
            "preview",
        ),
        ToolSpec(
            "orders_preview_change_butterfly",
            orders_preview_change_butterfly,
            OrdersPreviewChangeButterflyInput,
            "preview",
        ),
        ToolSpec(
            "orders_preview_condor", orders_preview_condor, OrdersPreviewCondorInput, "preview"
        ),
        ToolSpec(
            "orders_preview_change_condor",
            orders_preview_change_condor,
            OrdersPreviewChangeCondorInput,
            "preview",
        ),
        ToolSpec(
            "orders_preview_iron_butterfly",
            orders_preview_iron_butterfly,
            OrdersPreviewIronButterflyInput,
            "preview",
        ),
        ToolSpec(
            "orders_preview_change_iron_butterfly",
            orders_preview_change_iron_butterfly,
            OrdersPreviewChangeIronButterflyInput,
            "preview",
        ),
        ToolSpec(
            "orders_preview_iron_condor",
            orders_preview_iron_condor,
            OrdersPreviewIronCondorInput,
            "preview",
        ),
        ToolSpec(
            "orders_preview_change_iron_condor",
            orders_preview_change_iron_condor,
            OrdersPreviewChangeIronCondorInput,
            "preview",
        ),
        ToolSpec(
            "orders_preview_call_spread_short_put",
            orders_preview_call_spread_short_put,
            OrdersPreviewCallSpreadShortPutInput,
            "preview",
        ),
        ToolSpec(
            "orders_preview_change_call_spread_short_put",
            orders_preview_change_call_spread_short_put,
            OrdersPreviewChangeCallSpreadShortPutInput,
            "preview",
        ),
    ]
