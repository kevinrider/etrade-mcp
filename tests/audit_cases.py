"""Synthetic responses for the final offline protocol audit."""

from collections.abc import Callable
from threading import Event
from time import monotonic

import httpx

from tests.read_cases import CASES


def read_response(request: httpx.Request) -> httpx.Response:
    for case in CASES:
        if request.method == "GET" and request.url.path == case.path:
            assert request.url.params == httpx.QueryParams(case.params)
            return httpx.Response(200, json=case.payload)
    raise AssertionError("Unexpected synthetic read")


def page_response(request: httpx.Request) -> httpx.Response:
    assert request.method == "GET"
    path, params = request.url.path, request.url.params
    if path.endswith("/transactions.json"):
        marker = params.get("marker")
        assert marker in {None, "next-transaction"}
        return httpx.Response(
            200,
            json={
                "TransactionListResponse": {
                    "transaction": [{"transactionId": "boundary"}] if marker is None else [],
                    "marker": "next-transaction" if marker is None else "",
                    "moreTransactions": marker is None,
                }
            },
        )
    if path.endswith("/orders.json"):
        marker = params.get("marker")
        assert marker in {None, "next-order"}
        return httpx.Response(
            200,
            json={
                "OrdersResponse": {
                    "Order": [{"orderId": 17}] if marker is None else [],
                    "marker": "next-order" if marker is None else "",
                }
            },
        )
    if path.endswith("/portfolio.json"):
        page = params["pageNumber"]
        assert page in {"1", "2"}
        return httpx.Response(
            200,
            json={
                "PortfolioResponse": {
                    "AccountPortfolio": [
                        {
                            "accountId": "synthetic-account",
                            "nextPageNo": "2" if page == "1" else "",
                            "Position": [{"positionId": 1}] if page == "1" else [],
                        }
                    ]
                }
            },
        )
    raise AssertionError("Unexpected pagination request")


def wait_until(predicate: Callable[[], bool], timeout: float = 10) -> None:
    """Bounded file-based IPC wait, called in a thread rather than the event loop."""
    deadline = monotonic() + timeout
    pause = Event()
    while not predicate():
        if monotonic() >= deadline:
            raise TimeoutError("Synthetic worker did not reach the expected state")
        pause.wait(0.01)
