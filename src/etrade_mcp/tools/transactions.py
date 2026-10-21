"""Public transactions read tools; query and response handling remain in etrade-python."""

from typing import Any

from etrade_python import TransactionDetailsResponse, TransactionsResponse
from mcp.server.mcpserver.context import Context
from pydantic import Field

from etrade_mcp.inputs import TransactionListRequest, TransactionRequest
from etrade_mcp.responses import Response, WireModel
from etrade_mcp.server import Runtime, invoke


class TransactionsListInput(WireModel):
    account_id_key: str = Field(min_length=1)
    request: TransactionListRequest | None = None


async def transactions_list(
    ctx: Context[Runtime, Any], account_id_key: str, request: TransactionListRequest | None = None
) -> Response[TransactionsResponse]:
    """Read one transaction page. Markers are inclusive; boundary transactions are preserved."""
    state = ctx.request_context.lifespan_context
    return await invoke(
        "transactions_list", state, lambda: state.client.transactions.list(account_id_key, request)
    )


class TransactionsGetInput(WireModel):
    account_id_key: str = Field(min_length=1)
    transaction_id: str = Field(min_length=1)
    request: TransactionRequest | None = None


async def transactions_get(
    ctx: Context[Runtime, Any],
    account_id_key: str,
    transaction_id: str,
    request: TransactionRequest | None = None,
) -> Response[TransactionDetailsResponse]:
    """Read a transaction by its account and transaction ID, with optional store_id."""
    state = ctx.request_context.lifespan_context
    return await invoke(
        "transactions_get",
        state,
        lambda: state.client.transactions.get(account_id_key, transaction_id, request),
    )
