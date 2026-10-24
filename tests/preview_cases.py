"""Synthetic client-valid request contracts; no authenticated broker validation."""

from copy import deepcopy
from typing import Any


def equity(action: str = "BUY") -> dict[str, Any]:
    return {
        "product": {"symbol": "SYN", "security_type": "EQ"},
        "order_action": action,
        "quantity": "100",
    }


def option(action: str, strike: str, put_call: str = "PUT") -> dict[str, Any]:
    return {
        "product": {
            "symbol": "SYN",
            "security_type": "OPTN",
            "call_put": put_call,
            "expiry_year": 2027,
            "expiry_month": 1,
            "expiry_day": 15,
            "strike_price": strike,
        },
        "order_action": action,
        "quantity": "1",
    }


def request(
    order_type: str = "EQ",
    instruments: list[dict[str, Any]] | None = None,
    price_type: str = "LIMIT",
) -> dict[str, Any]:
    detail: dict[str, Any] = {
        "price_type": price_type,
        "order_term": "GOOD_FOR_DAY",
        "instruments": instruments if instruments is not None else [equity()],
    }
    if price_type in {"LIMIT", "NET_DEBIT", "NET_CREDIT"}:
        detail["limit_price"] = "1.1234567890123456789"
    return {"order_type": order_type, "client_order_id": "Synthetic123", "orders": [detail]}


REQUESTS = {
    "equity": request(),
    "single_option": request("OPTN", [option("SELL_OPEN", "100.125")]),
    "vertical": request(
        "SPREADS", [option("SELL_OPEN", "100"), option("BUY_OPEN", "95")], "NET_CREDIT"
    ),
    "three_leg": request(
        "BUTTERFLY",
        [option("BUY_OPEN", "95"), option("SELL_OPEN", "100"), option("BUY_OPEN", "105")],
        "NET_DEBIT",
    ),
    "iron_condor": request(
        "IRON_CONDOR",
        [
            option("BUY_OPEN", "90"),
            option("SELL_OPEN", "95"),
            option("SELL_OPEN", "105", "CALL"),
            option("BUY_OPEN", "110", "CALL"),
        ],
        "NET_CREDIT",
    ),
    "buy_write": request("BUY_WRITES", [equity(), option("SELL_OPEN", "110", "CALL")], "NET_DEBIT"),
    "mixed_close_open": request(
        "SPREADS", [option("BUY_CLOSE", "100"), option("SELL_OPEN", "95")], "NET_DEBIT"
    ),
}
REQUESTS["three_leg"]["orders"][0]["instruments"][1]["quantity"] = "2"
REQUESTS["mixed_close_open"]["orders"][0]["instruments"][1]["product"]["expiry_month"] = 2

all_fields = request("OPTN", [option("SELL_CLOSE", "100.125")])
all_fields["orders"][0].update(
    {
        "all_or_none": "false",
        "market_session": "EXTENDED",
        "stop_price": "",
        "stop_limit_price": "0.9999999999999999999",
        "offset_type": "TRAILING_STOP_CNST",
        "offset_value": "0.0000000000000000001",
        "routing_destination": "AUTO",
        "disclosure": {
            "eh_disclosure_flag": True,
            "ah_disclosure_flag": False,
            "conditional_disclosure_flag": False,
            "ao_disclosure_flag": False,
            "mf_fl_consent": False,
            "mf_eo_consent": False,
        },
        "conditionalLink": {"group": "synthetic", "sequence": 1},
    }
)
all_fields["orders"][0]["instruments"][0].update(
    {
        "quantity_type": "QUANTITY",
        "ordered_quantity": "1.000000000000000001",
        "lots": {"lots": [{"id": 7, "size": "0.1234567890123456789"}]},
        "osi_key": "SYN270115P00100125",
        "mf_transaction": "EXCHANGE",
        "reserve_order": False,
        "reserve_quantity": "0.000000000000000001",
        "legExtension": {"enabled": True, "amount": "0.1000000000000000001"},
    }
)
all_fields["orders"][0]["instruments"][0]["product"].update(
    {
        "security_sub_type": "STANDARD",
        "expiry_type": "MONTHLY",
    }
)
REQUESTS["all_fields"] = all_fields

all_owned = equity("SELL")
all_owned.pop("quantity")
all_owned["quantity_type"] = "ALL_I_OWN"
REQUESTS["all_owned"] = request(instruments=[all_owned], price_type="MARKET")

fund: dict[str, Any] = {
    "product": {"symbol": "SYNMF", "security_type": "MF"},
    "order_action": "BUY",
    "quantity_type": "DOLLAR",
    "mf_quantity": {"cash": "100.1234567890123456789", "margin": "0.00", "cusip": "SYNTHETIC"},
}
REQUESTS["fund_dollar"] = request("MF", [fund], "MARKET")

stop_limit = request()
stop_limit["orders"][0].update({"price_type": "STOP_LIMIT", "stop_price": "1.25"})
REQUESTS["stop_limit"] = stop_limit
REQUESTS["multiple_orders"] = request()
REQUESTS["multiple_orders"]["orders"].append(deepcopy(stop_limit["orders"][0]))

PREVIEW_RESPONSE: dict[str, Any] = {
    "PreviewOrderResponse": {
        "orderType": "SPREADS",
        "clientOrderId": "Synthetic123",
        "PreviewIds": [
            {"previewId": 101, "cashMargin": "CASH"},
            {"previewId": 102, "cashMargin": "MARGIN"},
        ],
        "previewTime": 1792173600000,
        "dstFlag": False,
        "accountId": "synthetic-account",
        "totalOrderValue": "100.1234567890123456789",
        "totalCommission": "0.0000000000000000001",
        "optionLevelCd": 3,
        "marginLevelCd": "MARGIN",
        "isEmployee": False,
        "commissionMessage": "Synthetic commission estimate",
        "Order": [
            {
                "priceType": "NET_CREDIT",
                "netPrice": "1.1234567890123456789",
                "Instrument": [
                    {
                        "Product": {"symbol": "SYN", "securityType": "OPTN"},
                        "orderAction": "SELL_OPEN",
                        "quantity": "1",
                    }
                ],
            }
        ],
        "Disclosure": {"ehDisclosureFlag": True},
        "settled": {"currentBp": "10000.000000000000000001"},
        "settledUnsettled": {"currentBp": "10001.000000000000000001"},
        "messageList": {
            "message": [{"code": 1, "type": "WARNING", "description": "Synthetic preview warning"}]
        },
    }
}
