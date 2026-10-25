"""Independently specified invalid tool arguments and their safe diagnostics."""

from copy import deepcopy
from dataclasses import dataclass
from typing import Any

from tests.preview_cases import REQUESTS
from tests.specialized_cases import CASES as SPECIALIZED

PRIVATE = "fake-private-submitted-value"


@dataclass(frozen=True)
class ValidationCase:
    name: str
    tool: str
    arguments: dict[str, Any]
    path: list[str | int]
    code: str


def equity(**updates: Any) -> dict[str, Any]:
    request = {
        "client_order_id": "Validation1",
        "symbol": "SYN",
        "order_action": "BUY",
        "quantity": "1",
        "price_type": "MARKET",
    }
    request.update(updates)
    return {"account_id_key": "synthetic-key", "request": request}


CASES = [
    ValidationCase(
        "quantity",
        "orders_preview_equity",
        equity(quantity="0"),
        ["request", "quantity"],
        "greater_than",
    ),
    ValidationCase(
        "numeric",
        "orders_preview_equity",
        equity(quantity=1),
        ["request", "quantity"],
        "decimal_string",
    ),
    ValidationCase(
        "action",
        "orders_preview_equity",
        equity(order_action=PRIVATE),
        ["request", "order_action"],
        "literal_error",
    ),
    ValidationCase(
        "client_id",
        "orders_preview_equity",
        equity(client_order_id="not-valid!"),
        ["request", "client_order_id"],
        "client_order_id_format",
    ),
    ValidationCase(
        "limit_required",
        "orders_preview_equity",
        equity(price_type="LIMIT"),
        ["request"],
        "limit_price_required",
    ),
    ValidationCase(
        "limit_unused",
        "orders_preview_equity",
        equity(limit_price="1"),
        ["request"],
        "limit_price_unused",
    ),
    ValidationCase(
        "stop_required",
        "orders_preview_equity",
        equity(price_type="STOP"),
        ["request"],
        "stop_price_required",
    ),
    ValidationCase(
        "unknown_root",
        "orders_preview_equity",
        {**equity(), PRIVATE: PRIVATE},
        [],
        "extra_forbidden",
    ),
    ValidationCase(
        "unknown_nested",
        "orders_preview_equity",
        equity(**{PRIVATE: PRIVATE}),
        ["request"],
        "extra_forbidden",
    ),
    ValidationCase(
        "flattened",
        "market_get_option_chain",
        {"symbol": "SYN", "expiry_year": 2026},
        [],
        "extra_forbidden",
    ),
    ValidationCase(
        "request_string",
        "market_get_option_chain",
        {"symbol": "SYN", "request": PRIVATE},
        ["request"],
        "model_type",
    ),
    ValidationCase(
        "year",
        "market_get_option_chain",
        {"symbol": "SYN", "request": {"expiry_year": 1800}},
        ["request", "expiry_year"],
        "greater_than_equal",
    ),
    ValidationCase(
        "year_type",
        "market_get_option_chain",
        {"symbol": "SYN", "request": {"expiry_year": PRIVATE}},
        ["request", "expiry_year"],
        "int_parsing",
    ),
    ValidationCase("client_symbol", "market_get_quote", {"symbol": " "}, ["symbol"], "nonempty"),
    ValidationCase(
        "client_symbols", "market_get_quotes", {"symbols": [" "]}, ["symbols"], "nonempty"
    ),
    ValidationCase("empty_symbols", "market_get_quotes", {"symbols": []}, ["symbols"], "too_short"),
    ValidationCase(
        "paired_dates",
        "transactions_list",
        {"account_id_key": "synthetic-key", "request": {"start_date": "01012026"}},
        ["request"],
        "paired_dates",
    ),
    ValidationCase(
        "client_account",
        "portfolio_get_positions",
        {"account_id_key": " "},
        ["account_id_key"],
        "nonempty",
    ),
]
missing = equity()
del missing["request"]["quantity"]
CASES.append(
    ValidationCase("missing", "orders_preview_equity", missing, ["request", "quantity"], "missing")
)
for name, updates, code in [
    ("whole_contracts", {"quantity": "1.5"}, "whole_contracts"),
    ("calendar", {"expiration": "2027-02-29"}, "calendar_date"),
    ("date_format", {"expiration": "2027-1-01"}, "string_pattern_mismatch"),
]:
    arguments = deepcopy(SPECIALIZED["single_option"][0]["arguments"])
    arguments["request"].update(updates)
    field = "quantity" if name == "whole_contracts" else "expiration"
    CASES.append(
        ValidationCase(name, "orders_preview_single_option", arguments, ["request", field], code)
    )
for name, updates, code in [
    ("ascending", {"lower_strike": "100"}, "ascending_strikes"),
    ("widths", {"upper_strike": "111"}, "equal_wing_widths"),
]:
    arguments = deepcopy(SPECIALIZED["butterfly"][0]["arguments"])
    arguments["request"].update(updates)
    CASES.append(ValidationCase(name, "orders_preview_butterfly", arguments, ["request"], code))
arguments = deepcopy(SPECIALIZED["vertical"][0]["arguments"])
arguments["request"]["buy_strike"] = arguments["request"]["sell_strike"]
CASES.append(
    ValidationCase(
        "distinct", "orders_preview_vertical", arguments, ["request"], "distinct_strikes"
    )
)
general_arguments: dict[str, Any] = {
    "account_id_key": "synthetic-key",
    "request": deepcopy(REQUESTS["equity"]),
}
general_arguments["request"]["clientOrderId"] = "OtherId"
CASES.append(
    ValidationCase(
        "aliases", "orders_preview", general_arguments, ["request"], "conflicting_aliases"
    )
)
general_arguments = {"account_id_key": "synthetic-key", "request": deepcopy(REQUESTS["equity"])}
general_arguments["request"]["orders"][0]["instruments"][0]["quantity"] = 1
CASES.append(
    ValidationCase(
        "nested",
        "orders_preview",
        general_arguments,
        ["request", "orders", 0, "instruments", 0, "quantity"],
        "decimal_string",
    )
)
