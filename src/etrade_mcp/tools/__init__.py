"""Read tool registry shared by HTTP and stdio."""

from etrade_mcp.server import ToolSpec
from etrade_mcp.tools.accounts import (
    AccountsGetBalanceInput,
    AccountsListInput,
    accounts_get_balance,
    accounts_list,
)
from etrade_mcp.tools.alerts import AlertsGetInput, AlertsListInput, alerts_get, alerts_list
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
from etrade_mcp.tools.orders import OrdersListInput, orders_list
from etrade_mcp.tools.portfolio import PortfolioGetPositionsInput, portfolio_get_positions
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
