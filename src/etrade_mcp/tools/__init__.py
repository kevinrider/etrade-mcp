"""Read and preview tool registries shared by HTTP and stdio."""

from etrade_mcp.server import ToolSpec
from etrade_mcp.tools.accounts import (
    AccountsGetBalanceInput,
    AccountsListInput,
    accounts_get_balance,
    accounts_list,
)
from etrade_mcp.tools.alerts import (
    AlertsDeleteInput,
    AlertsGetInput,
    AlertsListInput,
    alerts_delete,
    alerts_get,
    alerts_list,
)
from etrade_mcp.tools.market import (
    MarketGetOptionChainInput,
    MarketGetOptionExpirationsInput,
    MarketGetQuoteInput,
    MarketGetQuotesInput,
    MarketLookupProductInput,
    market_get_option_chain,
    market_get_option_expirations,
    market_get_quote,
    market_get_quotes,
    market_lookup_product,
)
from etrade_mcp.tools.orders import (
    OrdersCancelInput,
    OrdersListInput,
    OrdersPlaceChangeInput,
    OrdersPlaceInput,
    OrdersPreviewChangeInput,
    OrdersPreviewInput,
    orders_cancel,
    orders_list,
    orders_place,
    orders_place_change,
    orders_preview,
    orders_preview_change,
)
from etrade_mcp.tools.portfolio import PortfolioGetPositionsInput, portfolio_get_positions
from etrade_mcp.tools.specialized import specialized_preview_tools
from etrade_mcp.tools.transactions import (
    TransactionsGetInput,
    TransactionsListInput,
    transactions_get,
    transactions_list,
)


def read_tools() -> list[ToolSpec]:
    return [
        ToolSpec("accounts_list", accounts_list, AccountsListInput),
        ToolSpec("accounts_get_balance", accounts_get_balance, AccountsGetBalanceInput),
        ToolSpec("portfolio_get_positions", portfolio_get_positions, PortfolioGetPositionsInput),
        ToolSpec("transactions_list", transactions_list, TransactionsListInput),
        ToolSpec("transactions_get", transactions_get, TransactionsGetInput),
        ToolSpec("market_get_quote", market_get_quote, MarketGetQuoteInput),
        ToolSpec("market_get_quotes", market_get_quotes, MarketGetQuotesInput),
        ToolSpec("market_lookup_product", market_lookup_product, MarketLookupProductInput),
        ToolSpec(
            "market_get_option_expirations",
            market_get_option_expirations,
            MarketGetOptionExpirationsInput,
        ),
        ToolSpec("market_get_option_chain", market_get_option_chain, MarketGetOptionChainInput),
        ToolSpec("orders_list", orders_list, OrdersListInput),
        ToolSpec("alerts_list", alerts_list, AlertsListInput),
        ToolSpec("alerts_get", alerts_get, AlertsGetInput),
    ]


def preview_tools() -> list[ToolSpec]:
    return [
        *specialized_preview_tools(),
        ToolSpec("orders_preview", orders_preview, OrdersPreviewInput, "preview"),
        ToolSpec(
            "orders_preview_change", orders_preview_change, OrdersPreviewChangeInput, "preview"
        ),
    ]


def mutation_tools() -> list[ToolSpec]:
    return [
        ToolSpec("orders_place", orders_place, OrdersPlaceInput, "order_execution"),
        ToolSpec(
            "orders_place_change", orders_place_change, OrdersPlaceChangeInput, "order_execution"
        ),
        ToolSpec("orders_cancel", orders_cancel, OrdersCancelInput, "order_execution"),
        ToolSpec("alerts_delete", alerts_delete, AlertsDeleteInput, "alert_deletion"),
    ]
