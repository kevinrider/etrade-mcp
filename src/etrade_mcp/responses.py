"""Stable wire envelopes and conservative, non-retrying error classification."""

from __future__ import annotations

import json
import re
from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Generic, Literal, TypeVar

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
from mcp.types import CallToolResult, TextContent
from pydantic import BaseModel, ConfigDict, SerializeAsAny, ValidationError, model_validator

from etrade_mcp.config import ServerConfig

ErrorCode = Literal[
    "invalid_input",
    "authentication_required",
    "authorization_expired",
    "authentication_failed",
    "credential_coordination_failed",
    "execution_disabled",
    "tool_not_available",
    "broker_rejection",
    "rate_limited",
    "not_found",
    "service_unavailable",
    "invalid_broker_response",
    "transport_error",
    "uncertain_execution",
    "internal_error",
]
T = TypeVar("T", bound=BaseModel)


class WireModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, hide_input_in_errors=True)


class ResultMeta(WireModel):
    environment: str
    profile: str
    observed_at: datetime


class Failure(WireModel):
    code: ErrorCode
    message: str
    status_code: int | None = None
    broker_code: str | None = None
    request_id: str | None = None


class Response(WireModel, Generic[T]):
    ok: bool
    data: SerializeAsAny[T] | None = None
    error: Failure | None = None
    meta: ResultMeta

    @model_validator(mode="after")
    def consistent_result(self) -> Response[T]:
        if self.ok:
            if self.data is None or self.error is not None:
                raise ValueError("Successful responses require only data")
        elif self.data is not None or self.error is None:
            raise ValueError("Failed responses require only an error")
        return self


def metadata(config: ServerConfig) -> ResultMeta:
    return ResultMeta(
        environment=config.broker.environment.value,
        profile=config.server.profile,
        observed_at=datetime.now(UTC),
    )


def classified_error(
    error: Exception, *, mutation: bool = False, secrets: Sequence[str] = ()
) -> Failure:
    """Use static messages and structured metadata, never exception/broker text.

    Transport loss, malformed confirmations and 5xx failures after attempting a
    mutation are uncertain. Known local input/auth failures never claim a fill.
    """
    code: ErrorCode
    if isinstance(error, (ValidationError, ETradeValidationError)):
        code = "invalid_input"
    elif isinstance(error, CredentialCoordinationError):
        code = "credential_coordination_failed"
    elif isinstance(error, AuthenticationRequired):
        code = "authentication_required"
    elif isinstance(error, AuthorizationExpired):
        code = "authorization_expired"
    elif isinstance(error, ETradeAuthenticationError):
        code = "authentication_failed"
    elif mutation and (
        isinstance(error, (ETradeTransportError, ETradeResponseError, ETradeUnavailableError))
        or isinstance(error, ETradeApiError)
        and (error.status_code is None or error.status_code >= 500 or error.status_code == 408)
    ):
        code = "uncertain_execution"
    elif isinstance(error, ETradeRateLimitError):
        code = "rate_limited"
    elif isinstance(error, ETradeNotFoundError):
        code = "not_found"
    elif isinstance(error, ETradeUnavailableError):
        code = "service_unavailable"
    elif isinstance(error, ETradeResponseError):
        code = "invalid_broker_response"
    elif isinstance(error, ETradeTransportError):
        code = "transport_error"
    elif isinstance(error, ETradeApiError):
        code = "broker_rejection"
    else:
        code = "uncertain_execution" if mutation else "internal_error"
    messages = {
        "invalid_input": "Request input is invalid.",
        "authentication_required": "Run etrade auth login for the configured environment/profile.",
        "authorization_expired": "Broker authorization expired; run etrade auth login again.",
        "authentication_failed": "Broker authentication failed.",
        "credential_coordination_failed": "Credential access could not be coordinated.",
        "uncertain_execution": (
            "Submission outcome is uncertain. Reconcile before submitting again."
        ),
    }

    def safe_identifier(value: str | None, pattern: str) -> str | None:
        if value is None or re.fullmatch(pattern, value) is None:
            return None
        return None if any(secret and secret in value for secret in secrets) else value

    return Failure(
        code=code,
        message=messages.get(code, code.replace("_", " ").capitalize() + "."),
        status_code=error.status_code if isinstance(error, ETradeApiError) else None,
        # Client errors already redact broker OAuth secrets. Restrict reflected
        # metadata further and also exclude the separately configured HTTP secret.
        broker_code=(
            safe_identifier(error.broker_code, r"[0-9]{1,12}")
            if isinstance(error, ETradeApiError)
            else None
        ),
        request_id=(
            safe_identifier(error.request_id, r"[A-Za-z0-9][A-Za-z0-9._:-]{0,127}")
            if isinstance(error, ETradeApiError)
            else None
        ),
    )


def error_result(config: ServerConfig, failure: Failure) -> CallToolResult:
    envelope = Response[WireModel](ok=False, error=failure, meta=metadata(config))
    data = envelope.model_dump(mode="json")
    return CallToolResult(
        content=[TextContent(type="text", text=json.dumps(data))],
        structured_content=data,
        is_error=True,
    )
