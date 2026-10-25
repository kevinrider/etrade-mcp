"""Focused order contracts and deterministic construction using public client models."""

from __future__ import annotations

from datetime import date
from decimal import MAX_EMAX, MIN_EMIN, Decimal, localcontext
from fractions import Fraction
from typing import Annotated, Any, ClassVar, Literal

from etrade_python import (
    OrderDetailRequest,
    OrderInstrumentRequest,
    OrderProduct,
    PreviewOrderRequest,
)
from pydantic import Field, field_validator, model_validator

from etrade_mcp.inputs import DecimalString
from etrade_mcp.responses import WireModel

PositiveDecimal = Annotated[DecimalString, Field(gt=0, allow_inf_nan=False)]


class FamilyRequest(WireModel):
    family: ClassVar[str]
    order_type: ClassVar[str]
    client_order_id: str
    symbol: str = Field(min_length=1)
    order_term: Literal["GOOD_FOR_DAY", "GOOD_UNTIL_CANCEL"] = "GOOD_FOR_DAY"
    market_session: Literal["REGULAR", "EXTENDED", "EXTO"] = "REGULAR"
    all_or_none: bool | None = None
    limit_price: PositiveDecimal | None = None
    stop_price: PositiveDecimal | None = None

    @field_validator("client_order_id")
    @classmethod
    def normalize_client_id(cls, value: str) -> str:
        return PreviewOrderRequest.valid_client_order_id(value)

    @field_validator("symbol")
    @classmethod
    def normalize_symbol(cls, value: str) -> str:
        symbol = OrderProduct.model_validate({"symbol": value, "security_type": "EQ"}).symbol
        if symbol is None:
            raise ValueError("Symbol is required")
        return symbol

    @field_validator("*", mode="after")
    @classmethod
    def validate_family_field(cls, value: Any, info: Any) -> Any:
        if info.field_name == "expiration":
            if len(value) != 10 or value[4] != "-" or value[7] != "-":
                raise ValueError("Expiration must use YYYY-MM-DD")
            date.fromisoformat(value)
        if info.field_name in {"quantity", "option_quantity"} and cls.family != "equity":
            if value != value.to_integral_value():
                raise ValueError("Option quantities must be whole contracts")
        return value

    @model_validator(mode="after")
    def validate_contract(self) -> FamilyRequest:
        fields = self.model_dump()
        price = fields["price_type"]
        needs_limit = price in {"LIMIT", "STOP_LIMIT", "NET_DEBIT", "NET_CREDIT"}
        needs_stop = price in {"STOP", "STOP_LIMIT"}
        if (self.limit_price is not None) != needs_limit:
            raise ValueError("Provide limit_price only for limit or net debit/credit pricing")
        if (self.stop_price is not None) != needs_stop:
            raise ValueError("Provide stop_price only for STOP or STOP_LIMIT")
        geometry = {
            "butterfly": ("lower_strike", "middle_strike", "upper_strike"),
            "condor": (
                "lower_wing_strike",
                "lower_body_strike",
                "upper_body_strike",
                "upper_wing_strike",
            ),
            "iron_butterfly": ("lower_put_strike", "middle_strike", "upper_call_strike"),
            "iron_condor": (
                "lower_put_strike",
                "upper_put_strike",
                "lower_call_strike",
                "upper_call_strike",
            ),
        }
        strikes = [Fraction(fields[key]) for key in geometry.get(self.family, ())]
        if any(a >= b for a, b in zip(strikes, strikes[1:], strict=False)):
            raise ValueError("Strikes must strictly increase")
        if self.family in {"butterfly", "iron_butterfly"}:
            if strikes[1] - strikes[0] != strikes[2] - strikes[1]:
                raise ValueError("Butterfly wings must have equal widths")
        for buy, sell in (("buy_strike", "sell_strike"), ("buy_call_strike", "sell_call_strike")):
            if buy in fields and fields[buy] == fields[sell]:
                raise ValueError("Buy and sell strikes must differ")
        # Delegate the brokerage request's own validation to the public client.
        self.to_preview()
        return self

    def to_preview(self) -> PreviewOrderRequest:
        fields = self.model_dump()
        legs: list[OrderInstrumentRequest] = []

        def leg(
            security: str,
            action: str,
            quantity: Decimal,
            strike: str | None = None,
            right: str | None = None,
            ratio: int = 1,
        ) -> None:
            product: dict[str, Any] = {"symbol": self.symbol, "security_type": security}
            if security == "OPTN":
                assert strike is not None
                expiration = date.fromisoformat(fields["expiration"])
                product.update(
                    call_put=right or fields.get("call_put"),
                    expiry_year=expiration.year,
                    expiry_month=expiration.month,
                    expiry_day=expiration.day,
                    strike_price=fields[strike],
                )
            with localcontext() as context:
                context.prec = max(28, len(quantity.as_tuple().digits) + 2)
                context.Emax = MAX_EMAX
                context.Emin = MIN_EMIN
                sized = quantity if ratio == 1 else quantity * ratio
            legs.append(
                OrderInstrumentRequest.model_validate(
                    {
                        "product": product,
                        "order_action": action,
                        "quantity_type": "QUANTITY",
                        "quantity": sized,
                    }
                )
            )

        def option(role: str, strike: str, right: str | None = None, ratio: int = 1) -> None:
            closing = fields.get("position_effect") == "CLOSE"
            side = {"BUY": "SELL", "SELL": "BUY"}[role] if closing else role
            action = side + ("_CLOSE" if closing else "_OPEN")
            leg("OPTN", action, fields["quantity"], strike, right, ratio)

        if self.family == "equity":
            leg("EQ", fields["order_action"], fields["quantity"])
        elif self.family == "single_option":
            leg("OPTN", fields["order_action"], fields["quantity"], "strike_price")
        elif self.family == "buy_write":
            leg("EQ", "BUY", fields["stock_quantity"])
            leg("OPTN", "SELL_OPEN", fields["option_quantity"], "strike_price", "CALL")
        elif self.family == "vertical":
            option("BUY", "buy_strike")
            option("SELL", "sell_strike")
        elif self.family == "call_spread_short_put":
            option("BUY", "buy_call_strike", "CALL")
            option("SELL", "sell_call_strike", "CALL")
            option("SELL", "short_put_strike", "PUT")
        else:
            wing = fields["wing_action"]
            body = "SELL" if wing == "BUY" else "BUY"
            if self.family == "butterfly":
                option(wing, "lower_strike")
                option(body, "middle_strike", ratio=2)
                option(wing, "upper_strike")
            else:
                keys, rights = {
                    "condor": (
                        (
                            "lower_wing_strike",
                            "lower_body_strike",
                            "upper_body_strike",
                            "upper_wing_strike",
                        ),
                        (None,) * 4,
                    ),
                    "iron_butterfly": (
                        ("lower_put_strike", "middle_strike", "middle_strike", "upper_call_strike"),
                        ("PUT", "PUT", "CALL", "CALL"),
                    ),
                    "iron_condor": (
                        (
                            "lower_put_strike",
                            "upper_put_strike",
                            "lower_call_strike",
                            "upper_call_strike",
                        ),
                        ("PUT", "PUT", "CALL", "CALL"),
                    ),
                }[self.family]
                for role, key, right in zip((wing, body, body, wing), keys, rights, strict=True):
                    option(role, key, right)
        detail: dict[str, Any] = {
            key: fields[key]
            for key in (
                "price_type",
                "order_term",
                "market_session",
                "all_or_none",
                "limit_price",
                "stop_price",
            )
            if fields[key] is not None
        }
        detail["instruments"] = legs
        return PreviewOrderRequest.model_validate(
            {
                "order_type": self.order_type,
                "client_order_id": self.client_order_id,
                "orders": [OrderDetailRequest.model_validate(detail)],
            }
        )


class EquityRequest(FamilyRequest):
    family = "equity"
    order_type = "EQ"
    order_action: Literal["BUY", "SELL", "SELL_SHORT", "BUY_TO_COVER"]
    quantity: PositiveDecimal
    price_type: Literal["MARKET", "LIMIT", "STOP", "STOP_LIMIT"]


class OrdersPreviewEquityInput(WireModel):
    account_id_key: str = Field(min_length=1)
    request: EquityRequest


class OrdersPreviewChangeEquityInput(OrdersPreviewEquityInput):
    order_id: int = Field(gt=0, strict=True)


class SingleOptionRequest(FamilyRequest):
    family = "single_option"
    order_type = "OPTN"
    order_action: Literal["BUY_OPEN", "SELL_OPEN", "BUY_CLOSE", "SELL_CLOSE"]
    quantity: PositiveDecimal
    call_put: Literal["CALL", "PUT"]
    expiration: str = Field(pattern=r"^[0-9]{4}-[0-9]{2}-[0-9]{2}$")
    strike_price: PositiveDecimal
    price_type: Literal["MARKET", "LIMIT", "STOP", "STOP_LIMIT"]


class OrdersPreviewSingleOptionInput(WireModel):
    account_id_key: str = Field(min_length=1)
    request: SingleOptionRequest


class OrdersPreviewChangeSingleOptionInput(OrdersPreviewSingleOptionInput):
    order_id: int = Field(gt=0, strict=True)


class BuyWriteRequest(FamilyRequest):
    family = "buy_write"
    order_type = "BUY_WRITES"
    stock_quantity: PositiveDecimal
    option_quantity: PositiveDecimal
    expiration: str = Field(pattern=r"^[0-9]{4}-[0-9]{2}-[0-9]{2}$")
    strike_price: PositiveDecimal
    price_type: Literal["NET_DEBIT", "NET_CREDIT", "NET_EVEN"]


class OrdersPreviewBuyWriteInput(WireModel):
    account_id_key: str = Field(min_length=1)
    request: BuyWriteRequest


class OrdersPreviewChangeBuyWriteInput(OrdersPreviewBuyWriteInput):
    order_id: int = Field(gt=0, strict=True)


class VerticalRequest(FamilyRequest):
    family = "vertical"
    order_type = "SPREADS"
    quantity: PositiveDecimal
    call_put: Literal["CALL", "PUT"]
    expiration: str = Field(pattern=r"^[0-9]{4}-[0-9]{2}-[0-9]{2}$")
    buy_strike: PositiveDecimal
    sell_strike: PositiveDecimal
    position_effect: Literal["OPEN", "CLOSE"]
    price_type: Literal["NET_DEBIT", "NET_CREDIT", "NET_EVEN"]


class OrdersPreviewVerticalInput(WireModel):
    account_id_key: str = Field(min_length=1)
    request: VerticalRequest


class OrdersPreviewChangeVerticalInput(OrdersPreviewVerticalInput):
    order_id: int = Field(gt=0, strict=True)


class ButterflyRequest(FamilyRequest):
    family = "butterfly"
    order_type = "BUTTERFLY"
    quantity: PositiveDecimal
    call_put: Literal["CALL", "PUT"]
    expiration: str = Field(pattern=r"^[0-9]{4}-[0-9]{2}-[0-9]{2}$")
    lower_strike: PositiveDecimal
    middle_strike: PositiveDecimal
    upper_strike: PositiveDecimal
    wing_action: Literal["BUY", "SELL"]
    position_effect: Literal["OPEN", "CLOSE"]
    price_type: Literal["NET_DEBIT", "NET_CREDIT", "NET_EVEN"]


class OrdersPreviewButterflyInput(WireModel):
    account_id_key: str = Field(min_length=1)
    request: ButterflyRequest


class OrdersPreviewChangeButterflyInput(OrdersPreviewButterflyInput):
    order_id: int = Field(gt=0, strict=True)


class CondorRequest(FamilyRequest):
    family = "condor"
    order_type = "CONDOR"
    quantity: PositiveDecimal
    call_put: Literal["CALL", "PUT"]
    expiration: str = Field(pattern=r"^[0-9]{4}-[0-9]{2}-[0-9]{2}$")
    lower_wing_strike: PositiveDecimal
    lower_body_strike: PositiveDecimal
    upper_body_strike: PositiveDecimal
    upper_wing_strike: PositiveDecimal
    wing_action: Literal["BUY", "SELL"]
    position_effect: Literal["OPEN", "CLOSE"]
    price_type: Literal["NET_DEBIT", "NET_CREDIT", "NET_EVEN"]


class OrdersPreviewCondorInput(WireModel):
    account_id_key: str = Field(min_length=1)
    request: CondorRequest


class OrdersPreviewChangeCondorInput(OrdersPreviewCondorInput):
    order_id: int = Field(gt=0, strict=True)


class IronButterflyRequest(FamilyRequest):
    family = "iron_butterfly"
    order_type = "IRON_BUTTERFLY"
    quantity: PositiveDecimal
    expiration: str = Field(pattern=r"^[0-9]{4}-[0-9]{2}-[0-9]{2}$")
    lower_put_strike: PositiveDecimal
    middle_strike: PositiveDecimal
    upper_call_strike: PositiveDecimal
    wing_action: Literal["BUY", "SELL"]
    position_effect: Literal["OPEN", "CLOSE"]
    price_type: Literal["NET_DEBIT", "NET_CREDIT", "NET_EVEN"]


class OrdersPreviewIronButterflyInput(WireModel):
    account_id_key: str = Field(min_length=1)
    request: IronButterflyRequest


class OrdersPreviewChangeIronButterflyInput(OrdersPreviewIronButterflyInput):
    order_id: int = Field(gt=0, strict=True)


class IronCondorRequest(FamilyRequest):
    family = "iron_condor"
    order_type = "IRON_CONDOR"
    quantity: PositiveDecimal
    expiration: str = Field(pattern=r"^[0-9]{4}-[0-9]{2}-[0-9]{2}$")
    lower_put_strike: PositiveDecimal
    upper_put_strike: PositiveDecimal
    lower_call_strike: PositiveDecimal
    upper_call_strike: PositiveDecimal
    wing_action: Literal["BUY", "SELL"]
    position_effect: Literal["OPEN", "CLOSE"]
    price_type: Literal["NET_DEBIT", "NET_CREDIT", "NET_EVEN"]


class OrdersPreviewIronCondorInput(WireModel):
    account_id_key: str = Field(min_length=1)
    request: IronCondorRequest


class OrdersPreviewChangeIronCondorInput(OrdersPreviewIronCondorInput):
    order_id: int = Field(gt=0, strict=True)


class CallSpreadShortPutRequest(FamilyRequest):
    family = "call_spread_short_put"
    order_type = "SPREADS"
    quantity: PositiveDecimal
    expiration: str = Field(pattern=r"^[0-9]{4}-[0-9]{2}-[0-9]{2}$")
    buy_call_strike: PositiveDecimal
    sell_call_strike: PositiveDecimal
    short_put_strike: PositiveDecimal
    position_effect: Literal["OPEN", "CLOSE"]
    price_type: Literal["NET_DEBIT", "NET_CREDIT", "NET_EVEN"]


class OrdersPreviewCallSpreadShortPutInput(WireModel):
    account_id_key: str = Field(min_length=1)
    request: CallSpreadShortPutRequest


class OrdersPreviewChangeCallSpreadShortPutInput(OrdersPreviewCallSpreadShortPutInput):
    order_id: int = Field(gt=0, strict=True)
