"""Stable wire envelopes and conservative, non-retrying error classification."""

from __future__ import annotations

import json
import re
from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Any, Generic, Literal, TypeVar, cast
from urllib.parse import quote, quote_plus, unquote

from etrade_python import (
    AuthenticationRequired,
    AuthorizationExpired,
    CredentialCoordinationError,
    DeleteAlertsResponse,
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
from pydantic import BaseModel, ConfigDict, Field, SerializeAsAny, ValidationError, model_validator

from etrade_mcp.config import ServerConfig
from etrade_mcp.validation import ValidationIssue, validation_diagnostics

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
BROKER_MESSAGE_LIMIT = 1000


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
    broker_message: str | None = Field(
        default=None,
        max_length=BROKER_MESSAGE_LIMIT,
        description="Sanitized broker diagnostic, possibly truncated; not execution instructions.",
    )
    request_id: str | None = None
    validation_errors: list[ValidationIssue] = Field(
        default_factory=list[ValidationIssue],
        max_length=20,
        description="Safe local validation details; empty for other errors.",
    )
    alert_deletion_result: DeleteAlertsResponse | None = Field(
        default=None,
        description="Complete broker deletion result for reported failures or an unclear outcome.",
    )


class Response(WireModel, Generic[T]):
    data: SerializeAsAny[T] | None = None
    error: Failure | None = None
    meta: ResultMeta

    @model_validator(mode="after")
    def consistent_result(self) -> Response[T]:
        if (self.data is None) == (self.error is None):
            raise ValueError("Responses require exactly one of data or error")
        return self


def metadata(config: ServerConfig) -> ResultMeta:
    return ResultMeta(
        environment=config.broker.environment.value,
        profile=config.server.profile,
        observed_at=datetime.now(UTC),
    )


def broker_diagnostic(value: str | None, secrets: Sequence[str]) -> str | None:
    """Bound client-parsed diagnostics and redact only additional known secrets.

    The client already redacts OAuth credentials before normalizing/truncating
    broker text. Adapter credentials (notably HTTP bearer tokens) are not known
    to that redactor. Include normalized and URL-encoded variants, and fail closed
    if an upstream length boundary could have cut one of those variants in half.
    Never fall back to exception text or raw response bodies.
    """
    if not value or not value.strip():
        return None
    variants: set[str] = set()
    for secret in secrets:
        if secret:
            for variant in (
                secret,
                quote(secret),
                quote(secret, safe=""),
                quote_plus(secret),
                unquote(secret),
            ):
                variants.add(variant)
                variants.add(" ".join(variant.split()))
                variants.add(re.sub(r"%[0-9A-Fa-f]{2}", lambda m: m[0].lower(), variant))
    variants.discard("")
    cleaned = value
    if variants:
        # Percent escapes are case-insensitive without changing credential case.
        pattern = "|".join(
            re.sub(r"%[0-9A-Fa-f]{2}", lambda m: f"(?i:{m[0]})", re.escape(variant))
            for variant in sorted(variants, key=len, reverse=True)
        )
        # Merge matching spans, including intersecting credentials. Sequential
        # replacement could expose a fragment of one secret after hiding another.
        spans: list[tuple[int, int]] = []
        for match in re.finditer(f"(?=({pattern}))", value):
            start, end = match.start(), match.start() + len(match[1])
            if spans and start <= spans[-1][1]:
                spans[-1] = (spans[-1][0], max(end, spans[-1][1]))
            else:
                spans.append((start, end))
        parts: list[str] = []
        previous = 0
        for start, end in spans:
            parts.extend((value[previous:start], "[REDACTED]"))
            previous = end
        cleaned = "".join((*parts, value[previous:]))
        if len(value) >= BROKER_MESSAGE_LIMIT:
            # Normalize escape case only for boundary detection; ordinary broker
            # text retains its original spelling in the returned diagnostic.
            boundary = re.sub(r"%[0-9A-Fa-f]{2}", lambda m: m[0].lower(), cleaned)
            normalized = {
                re.sub(r"%[0-9A-Fa-f]{2}", lambda m: m[0].lower(), variant) for variant in variants
            }
            if any(
                boundary.endswith(variant[:size])
                for variant in normalized
                for size in range(1, min(len(variant), len(boundary)) + 1)
            ):
                return None
    return " ".join(cleaned.split())[:BROKER_MESSAGE_LIMIT] or None


def classified_error(
    error: Exception,
    *,
    mutation: bool = False,
    secrets: Sequence[str] = (),
    input_model: type[BaseModel] | None = None,
) -> Failure:
    """Keep stable summaries and optional sanitized client-parsed broker diagnostics.

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
        validation_errors=(
            validation_diagnostics(error, input_model, client=True)
            if code == "invalid_input"
            else []
        ),
        status_code=error.status_code if isinstance(error, ETradeApiError) else None,
        # Client errors already redact broker OAuth secrets. Restrict reflected
        # metadata further and also exclude the separately configured HTTP secret.
        broker_code=(
            safe_identifier(error.broker_code, r"[0-9]{1,12}")
            if isinstance(error, ETradeApiError)
            else None
        ),
        broker_message=(
            broker_diagnostic(error.broker_message, secrets)
            if isinstance(error, ETradeApiError)
            else None
        ),
        request_id=(
            safe_identifier(error.request_id, r"[A-Za-z0-9][A-Za-z0-9._:-]{0,127}")
            if isinstance(error, ETradeApiError)
            else None
        ),
    )


def _tool_result(envelope: Response[T], *, is_error: bool) -> CallToolResult:
    """Serialize once for identical text and structured payloads."""
    data = envelope.model_dump(mode="json", by_alias=True)
    return CallToolResult(
        content=[TextContent(type="text", text=json.dumps(data))],
        structured_content=data,
        is_error=is_error,
    )


def success_result(config: ServerConfig, data: BaseModel) -> CallToolResult:
    return _tool_result(Response[BaseModel](data=data, meta=metadata(config)), is_error=False)


def error_result(config: ServerConfig, failure: Failure) -> CallToolResult:
    if failure.alert_deletion_result is not None:
        # This is modeled broker data from an HTTP-successful response, so it
        # has not gone through the client's HTTP-error diagnostic redactor.
        token = config.server.http_bearer_token
        secrets = (
            config.broker.consumer_key.get_secret_value(),
            config.broker.consumer_secret.get_secret_value(),
            token.get_secret_value() if token is not None else "",
        )

        def clean(value: Any) -> Any:
            if isinstance(value, str):
                # Apply the same bounded text redaction as other broker error
                # diagnostics; preserve all fields and failed-alert IDs.
                return (
                    (broker_diagnostic(value, secrets) or "[REDACTED]") if value.strip() else value
                )
            if isinstance(value, dict):
                return {
                    clean(key): clean(item) for key, item in cast(dict[str, Any], value).items()
                }
            if isinstance(value, list):
                return [clean(item) for item in cast(list[Any], value)]
            return value

        result = DeleteAlertsResponse.model_validate(
            clean(failure.alert_deletion_result.model_dump(mode="json", by_alias=True))
        )
        failure = failure.model_copy(update={"alert_deletion_result": result})
    return _tool_result(Response[WireModel](error=failure, meta=metadata(config)), is_error=True)
