"""Strict public-client request subclasses; brokerage validation stays in the client."""

from decimal import Decimal
from typing import Annotated, Any, cast

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
from pydantic import BaseModel, BeforeValidator, ConfigDict, Field, WithJsonSchema, model_validator


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
