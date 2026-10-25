"""Synthetic broker diagnostics, including JSON/XML parsing and private body fields."""

from dataclasses import dataclass
from typing import Any
from xml.sax.saxutils import escape

import httpx
from etrade_python import ETradeSettings

RAW_SENTINEL = "fake-private-raw-response"


@dataclass(frozen=True)
class BrokerErrorCase:
    name: str
    status: int = 400
    broker_code: str | None = "51016"
    message: str | None = "Quantity cannot be changed for Buy Write/Spread Orders."
    expected_message: str | None = "Quantity cannot be changed for Buy Write/Spread Orders."
    category: str = "broker_rejection"
    xml: bool = False
    raw_body: str | None = None

    def response(self, settings: ETradeSettings) -> httpx.Response:
        if self.raw_body is not None:
            return httpx.Response(self.status, text=self.raw_body)
        message = self.message
        if message is not None:
            message = message.replace("{consumer_key}", settings.consumer_key.get_secret_value())
            message = message.replace(
                "{consumer_secret}", settings.consumer_secret.get_secret_value()
            )
        if self.xml:
            return httpx.Response(
                self.status,
                text=(
                    f"<Error><code>{escape(self.broker_code or '')}</code>"
                    f"<message>{escape(message or '')}</message>"
                    f"<private>{RAW_SENTINEL}</private></Error>"
                ),
                headers={"Content-Type": "application/xml"},
            )
        error: dict[str, Any] = {"private": RAW_SENTINEL}
        if self.broker_code is not None:
            error["code"] = self.broker_code
        if message is not None:
            error["message"] = message
        return httpx.Response(self.status, json={"Error": error}, headers={"Retry-After": "0"})


CASES = [
    BrokerErrorCase("quantity"),
    BrokerErrorCase(
        "xml",
        broker_code="640000",
        xml=True,
        message="Expiration unavailable — vérifiez la date.",
        expected_message="Expiration unavailable — vérifiez la date.",
    ),
    BrokerErrorCase(
        "auth",
        status=401,
        broker_code="100",
        category="authentication_failed",
        message="Authorization expired at broker.",
        expected_message="Authorization expired at broker.",
    ),
    BrokerErrorCase(
        "service",
        status=503,
        broker_code="41002",
        category="service_unavailable",
        message="Orders are temporarily unavailable.",
        expected_message="Orders are temporarily unavailable.",
    ),
    BrokerErrorCase(
        "unknown",
        broker_code="987654321",
        message="An unfamiliar broker rejection.",
        expected_message="An unfamiliar broker rejection.",
    ),
    BrokerErrorCase(
        "nonnumeric",
        broker_code="CUSTOM",
        message="Additional broker explanation.",
        expected_message="Additional broker explanation.",
    ),
    BrokerErrorCase("missing", message=None, expected_message=None),
    BrokerErrorCase("empty", message="", expected_message=None),
    BrokerErrorCase(
        "malformed", broker_code=None, message=None, expected_message=None, raw_body=RAW_SENTINEL
    ),
    BrokerErrorCase("blank", message=" \t\r\n ", expected_message=None),
    BrokerErrorCase(
        "spaces",
        message="Options unavailable.\n  Try another expiration.",
        expected_message="Options unavailable. Try another expiration.",
    ),
    BrokerErrorCase("long", message="Z" * 1400, expected_message="Z" * 1000),
    BrokerErrorCase(
        "credentials",
        message="Rejected credentials: {consumer_key} / {consumer_secret}.",
        expected_message="Rejected credentials: [REDACTED] / [REDACTED].",
    ),
]
