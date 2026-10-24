"""Public accounts read tools; query and response handling remain in etrade-python."""

from typing import Annotated, Any

from etrade_python import AccountBalanceResponse, AccountListResponse
from mcp.server.mcpserver.context import Context
from mcp.types import CallToolResult
from pydantic import Field

from etrade_mcp.inputs import BalanceRequest
from etrade_mcp.responses import Response, WireModel
from etrade_mcp.server import Runtime, invoke


class AccountsListInput(WireModel):
    pass


async def accounts_list(
    ctx: Context[Runtime, Any],
) -> Annotated[CallToolResult, Response[AccountListResponse]]:
    """List brokerage accounts."""
    state = ctx.request_context.lifespan_context
    return await invoke("accounts_list", state, lambda: state.client.accounts.list())


class AccountsGetBalanceInput(WireModel):
    account_id_key: str = Field(min_length=1)
    request: BalanceRequest | None = None


async def accounts_get_balance(
    ctx: Context[Runtime, Any], account_id_key: str, request: BalanceRequest | None = None
) -> Annotated[CallToolResult, Response[AccountBalanceResponse]]:
    """Read an account balance with all supported balance query fields."""
    state = ctx.request_context.lifespan_context
    return await invoke(
        "accounts_get_balance",
        state,
        lambda: state.client.accounts.get_balance(account_id_key, request),
    )
