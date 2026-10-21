"""Public portfolio read tools; query and response handling remain in etrade-python."""

from typing import Any

from etrade_python import PortfolioResponse
from mcp.server.mcpserver.context import Context
from pydantic import Field

from etrade_mcp.inputs import PositionsRequest
from etrade_mcp.responses import Response, WireModel
from etrade_mcp.server import Runtime, invoke


class PortfolioGetPositionsInput(WireModel):
    account_id_key: str = Field(min_length=1)
    request: PositionsRequest | None = None


async def portfolio_get_positions(
    ctx: Context[Runtime, Any], account_id_key: str, request: PositionsRequest | None = None
) -> Response[PortfolioResponse]:
    """Read one portfolio page, including requested views, lots, and totals. Follow
    next_page_no explicitly.
    """
    state = ctx.request_context.lifespan_context
    return await invoke(
        "portfolio_get_positions",
        state,
        lambda: state.client.portfolio.get_positions(account_id_key, request),
    )
