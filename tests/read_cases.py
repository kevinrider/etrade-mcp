"""Synthetic broker contracts: every public read request field has a wire assertion."""

from dataclasses import dataclass
from typing import Any

from etrade_python import (
    AccountBalanceRequest,
    AlertDetailsRequest,
    AlertsRequest,
    OptionChainRequest,
    OptionExpirationsRequest,
    OrdersRequest,
    PortfolioRequest,
    ProductLookupRequest,
    QuotesRequest,
    TransactionDetailsRequest,
    TransactionsRequest,
)
from pydantic import BaseModel


@dataclass(frozen=True)
class ReadCase:
    tool: str
    arguments: dict[str, Any]
    path: str
    params: dict[str, str]
    payload: dict[str, Any]
    request_model: type[BaseModel] | None = None


QUOTE = {"Product": {"symbol": "AAPL"}, "All": {"lastTrade": "0.1234567890123456789"}}
CASES = [
    ReadCase(
        "accounts_list",
        {},
        "/v1/accounts/list.json",
        {},
        {
            "AccountListResponse": {
                "Accounts": {
                    "Account": [{"accountId": "synthetic-account", "accountIdKey": "synthetic-key"}]
                }
            }
        },
    ),
    ReadCase(
        "accounts_get_balance",
        {
            "account_id_key": "synthetic-key",
            "request": {
                "inst_type": "BROKERAGE",
                "account_type": "MARGIN",
                "real_time_nav": True,
            },
        },
        "/v1/accounts/synthetic-key/balance.json",
        {
            "instType": "BROKERAGE",
            "accountType": "MARGIN",
            "realTimeNAV": "true",
        },
        {
            "BalanceResponse": {
                "accountId": "synthetic-account",
                "cash": {"moneyMktBalance": "0.1234567890123456789"},
            }
        },
        AccountBalanceRequest,
    ),
    ReadCase(
        "portfolio_get_positions",
        {
            "account_id_key": "synthetic-key",
            "request": {
                "count": 2,
                "sort_by": "SYMBOL",
                "sort_order": "ASC",
                "page_number": 2,
                "market_session": "REGULAR",
                "totals_required": True,
                "lots_required": False,
                "view": "QUICK",
            },
        },
        "/v1/accounts/synthetic-key/portfolio.json",
        {
            "count": "2",
            "sortBy": "SYMBOL",
            "sortOrder": "ASC",
            "pageNumber": "2",
            "marketSession": "REGULAR",
            "totalsRequired": "true",
            "lotsRequired": "false",
            "view": "QUICK",
        },
        {
            "PortfolioResponse": {
                "accountPortfolio": [
                    {
                        "accountId": "synthetic-account",
                        "nextPageNo": "3",
                        "next": "next-page",
                        "position": [{"positionId": 1, "quantity": "0.1234567890123456789"}],
                    }
                ]
            }
        },
        PortfolioRequest,
    ),
    ReadCase(
        "transactions_list",
        {
            "account_id_key": "synthetic-key",
            "request": {
                "marker": "boundary",
                "count": 2,
                "start_date": "01012026",
                "end_date": "01312026",
                "sort_order": "ASC",
            },
        },
        "/v1/accounts/synthetic-key/transactions.json",
        {
            "marker": "boundary",
            "count": "2",
            "startDate": "01012026",
            "endDate": "01312026",
            "sortOrder": "ASC",
        },
        {
            "TransactionListResponse": {
                "transaction": [
                    {"transactionId": "boundary", "amount": "0.1234567890123456789"},
                    {"transactionId": "next"},
                ],
                "marker": "next",
                "moreTransactions": True,
            }
        },
        TransactionsRequest,
    ),
    ReadCase(
        "transactions_get",
        {
            "account_id_key": "synthetic-key",
            "transaction_id": "synthetic-transaction",
            "request": {"store_id": "synthetic-store"},
        },
        "/v1/accounts/synthetic-key/transactions/synthetic-transaction.json",
        {
            "storeId": "synthetic-store",
        },
        {
            "TransactionDetailsResponse": {
                "transactionId": "synthetic-transaction",
                "amount": "0.1234567890123456789",
            }
        },
        TransactionDetailsRequest,
    ),
    ReadCase(
        "market_get_quote",
        {
            "symbol": "aapl",
            "request": {
                "detail_flag": "all",
                "require_earnings_date": False,
                "override_symbol_count": True,
                "skip_mini_options_check": False,
            },
        },
        "/v1/market/quote/AAPL.json",
        {
            "detailFlag": "ALL",
            "requireEarningsDate": "false",
            "overrideSymbolCount": "true",
            "skipMiniOptionsCheck": "false",
        },
        {"QuoteResponse": {"QuoteData": [QUOTE]}},
        QuotesRequest,
    ),
    ReadCase(
        "market_get_quotes",
        {
            "symbols": ["aapl", "msft"],
            "request": {
                "detail_flag": "options",
                "require_earnings_date": True,
                "override_symbol_count": False,
                "skip_mini_options_check": True,
            },
        },
        "/v1/market/quote/AAPL,MSFT.json",
        {
            "detailFlag": "OPTIONS",
            "requireEarningsDate": "true",
            "overrideSymbolCount": "false",
            "skipMiniOptionsCheck": "true",
        },
        {"QuoteResponse": {"QuoteData": [QUOTE]}},
        QuotesRequest,
    ),
    ReadCase(
        "market_lookup_product",
        {"search": "Synthetic & Co"},
        "/v1/market/lookup/Synthetic & Co.json",
        {},
        {"LookupResponse": {"Data": [{"symbol": "SYN", "description": "Synthetic & Co"}]}},
        ProductLookupRequest,
    ),
    ReadCase(
        "market_get_option_expirations",
        {"symbol": "aapl", "request": {"expiry_type": "weekly"}},
        "/v1/market/optionexpiredate.json",
        {"symbol": "AAPL", "expiryType": "WEEKLY"},
        {"OptionExpireDateResponse": {"ExpirationDate": [{"year": 2026, "month": 11, "day": 20}]}},
        OptionExpirationsRequest,
    ),
    ReadCase(
        "market_get_option_chain",
        {
            "symbol": "aapl",
            "request": {
                "expiry_year": 2026,
                "expiry_month": 11,
                "expiry_day": 20,
                "strike_price_near": "100.1234567890123456789",
                "no_of_strikes": 5,
                "include_weekly": True,
                "skip_adjusted": False,
                "option_category": "all",
                "chain_type": "put",
                "price_type": "all",
            },
        },
        "/v1/market/optionchains.json",
        {
            "symbol": "AAPL",
            "expiryYear": "2026",
            "expiryMonth": "11",
            "expiryDay": "20",
            "strikePriceNear": "100.1234567890123456789",
            "noOfStrikes": "5",
            "includeWeekly": "true",
            "skipAdjusted": "false",
            "optionCategory": "ALL",
            "chainType": "PUT",
            "priceType": "ALL",
        },
        {
            "OptionChainResponse": {
                "OptionPair": [
                    {
                        "Put": {
                            "symbol": "SYNTHETIC_OPTION",
                            "strikePrice": "100.1234567890123456789",
                        }
                    }
                ]
            }
        },
        OptionChainRequest,
    ),
    ReadCase(
        "orders_list",
        {
            "account_id_key": "synthetic-key",
            "request": {
                "marker": "order-marker",
                "count": 2,
                "status": "OPEN",
                "from_date": "01012026",
                "to_date": "01312026",
                "symbol": "AAPL",
                "security_type": "EQ",
                "transaction_type": "BUY",
                "market_session": "REGULAR",
            },
        },
        "/v1/accounts/synthetic-key/orders.json",
        {
            "marker": "order-marker",
            "count": "2",
            "status": "OPEN",
            "fromDate": "01012026",
            "toDate": "01312026",
            "symbol": "AAPL",
            "securityType": "EQ",
            "transactionType": "BUY",
            "marketSession": "REGULAR",
        },
        {"OrdersResponse": {"Order": [{"orderId": 123}], "marker": "next-order"}},
        OrdersRequest,
    ),
    ReadCase(
        "alerts_list",
        {
            "request": {
                "count": 2,
                "category": "account",
                "status": "unread",
                "direction": "asc",
                "search": "Synthetic",
            }
        },
        "/v1/user/alerts.json",
        {
            "count": "2",
            "category": "ACCOUNT",
            "status": "UNREAD",
            "direction": "ASC",
            "search": "Synthetic",
        },
        {"AlertsResponse": {"totalAlerts": 1, "Alert": [{"id": 1, "subject": "Synthetic"}]}},
        AlertsRequest,
    ),
    ReadCase(
        "alerts_get",
        {"alert_id": 1, "request": {"html_tags": False}},
        "/v1/user/alerts/1.json",
        {"htmlTags": "false"},
        {"AlertDetailsResponse": {"id": 1, "msgText": "Synthetic alert"}},
        AlertDetailsRequest,
    ),
]
