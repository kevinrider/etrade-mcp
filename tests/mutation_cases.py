"""Synthetic mutation cases; no authenticated broker validation or customer data."""

import json
from copy import deepcopy
from dataclasses import dataclass
from typing import Any

import httpx

from tests.preview_cases import PREVIEW_RESPONSE
from tests.specialized_cases import CASES

IDS = [{"previewId": 101}, {"previewId": 102}]
BODY: dict[str, Any] = {
    **deepcopy(CASES["equity"][0]["canonical_preview_request"]),
    "PreviewIds": IDS,
}
PLACE = {
    "PlaceOrderResponse": {
        "orderType": "EQ",
        "accountId": "fake-private-account-response",
        "OrderIds": [{"orderId": 701}, {"orderId": 702}],
        "totalCommission": "0.1234567890123456789",
        "messageList": {
            "Message": [
                {"code": 1027, "type": "WARNING", "description": "Synthetic acceptance warning"}
            ]
        },
    }
}
CANCEL = {
    "CancelOrderResponse": {
        "orderId": 17,
        "accountId": "fake-private-account-response",
        "Messages": {
            "Message": [
                {"code": 5011, "type": "WARNING", "description": "Synthetic cancellation pending"}
            ]
        },
    }
}
DELETE = {"DeleteAlertsResponse": {"result": "SUCCESS"}}


@dataclass(frozen=True)
class MutationCase:
    tool: str
    arguments: dict[str, Any]
    method: str
    path: str
    body: dict[str, Any] | None


MUTATIONS = [
    MutationCase(
        "orders_place",
        {"account_id_key": "synthetic-key", "request": BODY},
        "POST",
        "/v1/accounts/synthetic-key/orders/place.json",
        {"PlaceOrderRequest": BODY},
    ),
    MutationCase(
        "orders_place_change",
        {"account_id_key": "synthetic-key", "order_id": 17, "request": BODY},
        "PUT",
        "/v1/accounts/synthetic-key/orders/17/change/place.json",
        {"PlaceOrderRequest": BODY},
    ),
    MutationCase(
        "orders_cancel",
        {"account_id_key": "synthetic-key", "order_id": 17},
        "PUT",
        "/v1/accounts/synthetic-key/orders/cancel.json",
        {"CancelOrderRequest": {"orderId": 17}},
    ),
    MutationCase(
        "alerts_delete", {"alert_ids": [101, 102]}, "DELETE", "/v1/user/alerts/101,102.json", None
    ),
]


def response(request: httpx.Request) -> httpx.Response:
    path = request.url.path
    if path.endswith("/preview.json"):
        return httpx.Response(200, json=PREVIEW_RESPONSE)
    if path.endswith("/place.json"):
        return httpx.Response(200, json=PLACE)
    if path.endswith("/cancel.json"):
        assert json.loads(request.content) == {"CancelOrderRequest": {"orderId": 17}}
        return httpx.Response(200, json=CANCEL)
    if path.startswith("/v1/user/alerts/") and request.method == "DELETE":
        if path.endswith("/101,999.json"):
            return httpx.Response(
                200,
                json={
                    "DeleteAlertsResponse": {
                        "result": "ERROR",
                        "failedAlerts": {"alertId": [999]},
                    }
                },
            )
        if path.endswith("/998.json"):
            return httpx.Response(200, json={"DeleteAlertsResponse": {"result": "UNKNOWN"}})
        return httpx.Response(200, json=DELETE)
    raise AssertionError("Unexpected mocked broker request")
