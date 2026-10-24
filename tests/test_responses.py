from decimal import Decimal
from typing import Any

import pytest
from etrade_python import (
    AuthenticationRequired,
    AuthorizationExpired,
    CredentialCoordinationError,
    ETradeApiError,
    ETradeAuthenticationError,
    ETradeNotFoundError,
    ETradeRateLimitError,
    ETradeResponseError,
    ETradeTransportError,
    ETradeUnavailableError,
    ETradeValidationError,
)
from pydantic import ValidationError

from etrade_mcp.config import ServerConfig
from etrade_mcp.responses import Response, WireModel, classified_error, error_result, metadata


@pytest.mark.parametrize(
    "error,code,mutation",
    [
        (ETradeValidationError("fake-secret"), "invalid_input", False),
        (AuthenticationRequired("fake-secret"), "authentication_required", True),
        (AuthorizationExpired("fake-secret"), "authorization_expired", True),
        (CredentialCoordinationError("fake-secret"), "credential_coordination_failed", True),
        (ETradeAuthenticationError("fake-secret"), "authentication_failed", True),
        (ETradeTransportError("fake-secret"), "transport_error", False),
        (ETradeTransportError("fake-secret"), "uncertain_execution", True),
        (ETradeResponseError("fake-secret"), "invalid_broker_response", False),
        (ETradeResponseError("fake-secret"), "uncertain_execution", True),
        (ETradeUnavailableError("fake-secret"), "service_unavailable", False),
        (ETradeUnavailableError("fake-secret"), "uncertain_execution", True),
        (ETradeRateLimitError("fake-secret", status_code=429), "rate_limited", True),
        (ETradeNotFoundError("fake-secret", status_code=404), "not_found", True),
        (ETradeApiError("fake-secret", status_code=400), "broker_rejection", True),
        (ETradeApiError("fake-secret", status_code=408), "uncertain_execution", True),
        (ETradeApiError("fake-secret", status_code=503), "uncertain_execution", True),
        (ETradeApiError("fake-secret"), "uncertain_execution", True),
        (ETradeApiError("fake-secret"), "broker_rejection", False),
        (RuntimeError("fake-secret"), "internal_error", False),
        (RuntimeError("fake-secret"), "uncertain_execution", True),
    ],
)
def test_error_categories(
    error: Exception, code: str, mutation: bool, config: ServerConfig
) -> None:
    failure = classified_error(error, mutation=mutation)
    assert failure.code == code
    result = error_result(config, failure)
    assert result.is_error
    assert "fake-secret" not in result.model_dump_json()


@pytest.mark.parametrize("code,expected", [("123", "123"), ("fake-secret", None), (None, None)])
def test_broker_metadata_is_restricted(code: str | None, expected: str | None) -> None:
    failure = classified_error(
        ETradeApiError(
            "fake-secret", broker_code=code, broker_message="fake-secret", request_id="fake-secret"
        ),
        secrets=("fake-secret",),
    )
    assert failure.broker_code == expected
    assert failure.request_id is None
    assert "fake-secret" not in failure.model_dump_json()


def test_safe_broker_request_id() -> None:
    failure = classified_error(ETradeApiError("failure", request_id="broker-123:abc"))
    assert failure.request_id == "broker-123:abc"
    assert classified_error(ETradeApiError("failure", request_id="[REDACTED]")).request_id is None


class Money(WireModel):
    amount: Decimal


def test_precision_and_response_invariants(config: ServerConfig) -> None:
    response = Response[Money](
        data=Money(amount=Decimal("0.1234567890123456789")), meta=metadata(config)
    )
    assert '"0.1234567890123456789"' in response.model_dump_json()
    assert "ok" not in response.model_dump()
    failure = classified_error(RuntimeError())
    assert Response[Money](error=failure, meta=metadata(config)).data is None
    for values in (
        {},
        {"data": None, "error": None},
        {"data": response.data, "error": failure},
        {"ok": True, "data": response.data},
        {"ok": False, "error": failure},
    ):
        options: dict[str, Any] = values
        with pytest.raises(ValidationError):
            Response[Money](meta=metadata(config), **options)
