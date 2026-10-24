"""Public market read tools; query and response handling remain in etrade-python."""

from typing import Annotated, Any

from etrade_python import (
    OptionChainResponse,
    OptionExpirationsResponse,
    ProductLookupResponse,
    Quote,
    QuotesResponse,
)
from mcp.server.mcpserver.context import Context
from mcp.types import CallToolResult
from pydantic import Field

from etrade_mcp.inputs import ChainRequest, ExpirationsRequest, LookupRequest, QuoteRequest
from etrade_mcp.responses import Response, WireModel
from etrade_mcp.server import Runtime, invoke


class MarketGetQuoteInput(WireModel):
    symbol: str = Field(min_length=1)
    request: QuoteRequest | None = None


async def market_get_quote(
    ctx: Context[Runtime, Any], symbol: str, request: QuoteRequest | None = None
) -> Annotated[CallToolResult, Response[Quote]]:
    """Read a single symbol quote with all supported quote flags."""
    state = ctx.request_context.lifespan_context
    return await invoke(
        "market_get_quote", state, lambda: state.client.market.get_quote(symbol, request)
    )


class MarketGetQuotesInput(WireModel):
    symbols: list[str] = Field(min_length=1)
    request: QuoteRequest | None = None


async def market_get_quotes(
    ctx: Context[Runtime, Any], symbols: list[str], request: QuoteRequest | None = None
) -> Annotated[CallToolResult, Response[QuotesResponse]]:
    """Read multiple symbol quotes. The client permits 25 symbols, or 50 with
    override_symbol_count.
    """
    state = ctx.request_context.lifespan_context
    return await invoke(
        "market_get_quotes", state, lambda: state.client.market.get_quotes(symbols, request)
    )


class MarketLookupProductInput(LookupRequest):
    pass


async def market_lookup_product(
    ctx: Context[Runtime, Any], search: str
) -> Annotated[CallToolResult, Response[ProductLookupResponse]]:
    """Search for products using the client search validation and URL encoding."""
    state = ctx.request_context.lifespan_context
    return await invoke(
        "market_lookup_product", state, lambda: state.client.market.lookup_product(search)
    )


class MarketGetOptionExpirationsInput(WireModel):
    symbol: str = Field(min_length=1)
    request: ExpirationsRequest | None = None


async def market_get_option_expirations(
    ctx: Context[Runtime, Any], symbol: str, request: ExpirationsRequest | None = None
) -> Annotated[CallToolResult, Response[OptionExpirationsResponse]]:
    """Read option expiration dates with optional expiry_type selection."""
    state = ctx.request_context.lifespan_context
    return await invoke(
        "market_get_option_expirations",
        state,
        lambda: state.client.market.get_option_expirations(symbol, request),
    )


class MarketGetOptionChainInput(WireModel):
    symbol: str = Field(min_length=1)
    request: ChainRequest | None = None


async def market_get_option_chain(
    ctx: Context[Runtime, Any], symbol: str, request: ChainRequest | None = None
) -> Annotated[CallToolResult, Response[OptionChainResponse]]:
    """Read an option chain with all supported expiry, strike, weekly, and adjusted filters.
    Monetary inputs are decimal strings.
    """
    state = ctx.request_context.lifespan_context
    return await invoke(
        "market_get_option_chain",
        state,
        lambda: state.client.market.get_option_chain(symbol, request),
    )
