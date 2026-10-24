"""Strict public-client request subclasses; brokerage validation stays in the client."""

from decimal import Decimal
from typing import Annotated, Any, cast

from etrade_python import (
    AccountBalanceRequest,
    AlertDetailsRequest,
    AlertsRequest,
    Disclosure,
    MFQuantity,
    OptionChainRequest,
    OptionExpirationsRequest,
    OrderDetailRequest,
    OrderInstrumentRequest,
    OrderLot,
    OrderLots,
    OrderProduct,
    OrdersRequest,
    PortfolioRequest,
    PreviewOrderRequest,
    ProductLookupRequest,
    QuotesRequest,
    TransactionDetailsRequest,
    TransactionsRequest,
)
from pydantic import (
    BaseModel,
    BeforeValidator,
    ConfigDict,
    Field,
    ValidateAs,
    WithJsonSchema,
    model_validator,
)


class StrictRequest(BaseModel):
    model_config = ConfigDict(
        extra="forbid", frozen=True, populate_by_name=True, hide_input_in_errors=True
    )

    @model_validator(mode="before")
    @classmethod
    def unambiguous_aliases(cls, value: Any) -> Any:
        if isinstance(value, dict):
            value = cast(dict[str, Any], value)
            for name, field in cls.model_fields.items():
                alias = field.alias
                if alias and alias != name and name in value and alias in value:
                    if value[name] != value[alias]:
                        raise ValueError("Conflicting field spellings")
                    value = {key: item for key, item in value.items() if key != alias}
        return value


def decimal_string(value: Any) -> Any:
    if not isinstance(value, str):
        raise ValueError("A decimal string is required")
    return value


DecimalString = Annotated[
    Decimal, BeforeValidator(decimal_string), WithJsonSchema({"type": "string"}, mode="validation")
]


class BalanceRequest(AccountBalanceRequest, StrictRequest):
    pass


class PositionsRequest(PortfolioRequest, StrictRequest):
    pass


class TransactionListRequest(TransactionsRequest, StrictRequest):
    pass


class TransactionRequest(TransactionDetailsRequest, StrictRequest):
    pass


class QuoteRequest(QuotesRequest, StrictRequest):
    pass


class LookupRequest(ProductLookupRequest, StrictRequest):
    pass


class ExpirationsRequest(OptionExpirationsRequest, StrictRequest):
    pass


class ChainRequest(OptionChainRequest, StrictRequest):
    strike_price_near: DecimalString | None = Field(default=None, ge=0)


class OrderListRequest(OrdersRequest, StrictRequest):
    pass


class AlertListRequest(AlertsRequest, StrictRequest):
    pass


class AlertRequest(AlertDetailsRequest, StrictRequest):
    pass


class PreviewProduct(OrderProduct, StrictRequest):
    strike_price: DecimalString | None = Field(default=None, alias="strikePrice")


class PreviewLot(OrderLot, StrictRequest):
    size: DecimalString | None = None


def _validated_model(value: BaseModel) -> BaseModel:
    # ValidateAs keeps the public client field types while using stricter
    # subclasses for input validation and schemas. Return those models intact.
    return value


class PreviewLots(OrderLots, StrictRequest):
    lots: list[Annotated[OrderLot, ValidateAs(PreviewLot, _validated_model)]] = Field(
        default_factory=list[OrderLot], alias="lot"
    )

    @model_validator(mode="before")
    @classmethod
    def unambiguous_lots(cls, value: Any) -> Any:
        if isinstance(value, dict):
            value = cast(dict[str, Any], value)
            data = value
            names = [name for name in ("lot", "lots", "Lot") if name in data]
            if names:
                if any(data[name] != data[names[0]] for name in names[1:]):
                    raise ValueError("Conflicting field spellings")
                return {
                    **{name: item for name, item in data.items() if name not in names},
                    "lot": data[names[0]],
                }
        return value


class PreviewMFQuantity(MFQuantity, StrictRequest):
    cash: DecimalString | None = None
    margin: DecimalString | None = None


class PreviewDisclosure(Disclosure, StrictRequest):
    pass


class PreviewInstrument(OrderInstrumentRequest, StrictRequest):
    # The client deliberately permits extensions at this level.
    model_config = ConfigDict(extra="allow")

    product: Annotated[OrderProduct, ValidateAs(PreviewProduct, _validated_model)] = Field(
        alias="Product"
    )
    quantity: DecimalString | None = None
    ordered_quantity: DecimalString | None = Field(default=None, alias="orderedQuantity")
    reserve_quantity: DecimalString | None = Field(default=None, alias="reserveQuantity")
    lots: Annotated[OrderLots, ValidateAs(PreviewLots, _validated_model)] | None = None
    mf_quantity: Annotated[MFQuantity, ValidateAs(PreviewMFQuantity, _validated_model)] | None = (
        Field(default=None, alias="mfQuantity")
    )


class PreviewDetail(OrderDetailRequest, StrictRequest):
    model_config = ConfigDict(extra="allow")

    instruments: list[
        Annotated[OrderInstrumentRequest, ValidateAs(PreviewInstrument, _validated_model)]
    ] = Field(alias="Instrument")
    disclosure: Annotated[Disclosure, ValidateAs(PreviewDisclosure, _validated_model)] | None = None
    limit_price: DecimalString | None = Field(default=None, alias="limitPrice")
    stop_limit_price: DecimalString | None = Field(default=None, alias="stopLimitPrice")
    offset_value: DecimalString | None = Field(default=None, alias="offsetValue")
    stop_price: (
        Annotated[Decimal | str, WithJsonSchema({"type": "string"}, mode="validation")] | None
    ) = Field(default=None, alias="stopPrice")

    @model_validator(mode="before")
    @classmethod
    def stop_price_string(cls, value: Any) -> Any:
        # Guard the raw input before the inherited client parser converts it
        # to Decimal. The client retains its blank-stop and price-shape rules.
        if isinstance(value, dict):
            value = cast(dict[str, Any], value)
            data = value
            for name in ("stop_price", "stopPrice"):
                if name in data and data[name] is not None:
                    decimal_string(data[name])
        return value


class PreviewRequest(PreviewOrderRequest, StrictRequest):
    orders: list[Annotated[OrderDetailRequest, ValidateAs(PreviewDetail, _validated_model)]] = (
        Field(alias="Order")
    )
