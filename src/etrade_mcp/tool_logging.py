"""Opt-in, bounded tool argument previews. Never enable protocol/wire logging."""

from __future__ import annotations

import json
import logging
import math
import re
import sys
from collections.abc import Sequence
from typing import Any, cast, get_args, get_origin
from uuid import uuid4

from mcp.types import CallToolResult
from pydantic import BaseModel

from etrade_mcp.config import ServerConfig
from etrade_mcp.responses import ErrorCode, broker_diagnostic
from etrade_mcp.validation import (
    BUILTIN_MESSAGES,
    CLIENT_REASONS,
    CUSTOM_MESSAGES,
    Node,
    alternatives,
    project_path,
)

LOGGER = logging.getLogger("etrade_mcp.tool_calls")
MAX_EVENT_BYTES = 16384
MAX_DEPTH = 12
MAX_ITEMS = 10
MAX_FIELDS = 32
MAX_NODES = 200
MAX_STRING = 256
MAX_JSON_STRING = 8192
REDACTED = "[REDACTED]"
NUMERIC_FIELDS = frozenset(
    {
        "quantity",
        "ordered_quantity",
        "reserve_quantity",
        "stock_quantity",
        "option_quantity",
        "limit_price",
        "stop_price",
        "stop_limit_price",
        "strike_price",
        "strike_price_near",
        "buy_strike",
        "sell_strike",
        "lower_strike",
        "middle_strike",
        "upper_strike",
        "lower_wing_strike",
        "lower_body_strike",
        "upper_body_strike",
        "upper_wing_strike",
        "lower_put_strike",
        "upper_put_strike",
        "lower_call_strike",
        "upper_call_strike",
        "buy_call_strike",
        "sell_call_strike",
        "short_put_strike",
        "offset_value",
        "expiry_year",
        "expiry_month",
        "expiry_day",
        "no_of_strikes",
        "count",
        "page_number",
    }
)
SETTING_FIELDS = frozenset(
    {
        "order_type",
        "order_action",
        "price_type",
        "order_term",
        "market_session",
        "security_type",
        "security_sub_type",
        "call_put",
        "position_effect",
        "wing_action",
        "quantity_type",
        "chain_type",
        "option_category",
        "expiry_type",
        "offset_type",
        "routing_destination",
        "detail_flag",
        "sort_order",
        "status",
        "inst_type",
    }
)
VALIDATION_CODES = frozenset(
    {
        *BUILTIN_MESSAGES,
        *CUSTOM_MESSAGES,
        *(code for code, _ in CLIENT_REASONS.values()),
        "invalid_value",
        "unsupported_choice",
        "additional_errors",
        "positive_integer",
        "literal_error",
        "greater_than",
        "greater_than_equal",
        "less_than",
        "less_than_equal",
        "string_too_short",
        "string_too_long",
        "too_short",
        "too_long",
        "string_pattern_mismatch",
    }
)


class QuietStreamHandler(logging.StreamHandler[Any]):
    def handleError(self, record: logging.LogRecord) -> None:
        # A diagnostic sink failure must not print tracebacks or affect a tool.
        pass


def configure_tool_logging(enabled: bool) -> None:
    """CLI-owned stderr handler. Library callers can configure LOGGER themselves."""
    for handler in list(LOGGER.handlers):
        LOGGER.removeHandler(handler)
        handler.close()
    LOGGER.propagate = False
    LOGGER.setLevel(logging.INFO if enabled else logging.CRITICAL)
    if enabled:
        handler = QuietStreamHandler(sys.stderr)
        handler.setFormatter(logging.Formatter("%(message)s"))
        LOGGER.addHandler(handler)


def json_type(value: Any) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, (int, float)):
        return "number"
    if isinstance(value, str):
        return "string"
    if isinstance(value, dict):
        return "object"
    if isinstance(value, list):
        return "array"
    return "unsupported"


def child_fields(nodes: list[Node]) -> dict[str, tuple[str, list[Node]]]:
    fields: dict[str, tuple[str, list[Node]]] = {}
    for node in nodes:
        for choice in alternatives(node):
            model = choice.annotation
            if isinstance(model, type) and issubclass(model, BaseModel):
                for name, info in model.model_fields.items():
                    children = [Node(info.annotation, tuple(info.metadata))]
                    for alias in (name, info.alias, info.validation_alias):
                        if isinstance(alias, str) and len(alias) <= 64:
                            fields[alias] = (name, children)
    return fields


def sensitive(name: str) -> bool:
    return name.endswith(("_id", "_ids", "_key")) or any(
        part in name
        for part in (
            "account",
            "token",
            "secret",
            "credential",
            "authorization",
            "password",
            "verifier",
            "signature",
            "cusip",
            "osi_key",
        )
    )


class ArgumentPreview:
    def __init__(self, secrets: Sequence[str]) -> None:
        self.secrets = secrets
        self.remaining = MAX_NODES

    def scalar(self, value: Any, name: str) -> Any:
        if sensitive(name):
            return REDACTED
        if isinstance(value, bool):
            return value
        if isinstance(value, (int, float)):
            if name not in NUMERIC_FIELDS:
                return REDACTED
            if isinstance(value, int) and value.bit_length() > 256:
                return REDACTED
            if isinstance(value, float) and not math.isfinite(value):
                return REDACTED
            # Even numeric values can match a configured secret.
            if broker_diagnostic(str(value), self.secrets) != str(value):
                return REDACTED
            return value
        if not isinstance(value, str):
            return None if value is None else REDACTED
        cleaned = broker_diagnostic(value, self.secrets)
        if cleaned is None:
            return REDACTED
        if cleaned != value:
            # Preserve neither secret fragments nor misleading normalized text.
            return REDACTED
        if name in {"symbol", "symbols"}:
            permitted = bool(re.fullmatch(r"[A-Za-z0-9.^:/_-]{1,64}", cleaned))
        elif name in NUMERIC_FIELDS:
            permitted = bool(
                re.fullmatch(r"[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?", cleaned)
            )
        elif name in SETTING_FIELDS:
            permitted = bool(re.fullmatch(r"[A-Za-z0-9_-]{1,64}", cleaned))
        elif name == "expiration":
            permitted = bool(re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", cleaned))
        else:
            permitted = False
        return cleaned[:MAX_STRING] if permitted else REDACTED

    def render(
        self, value: Any, nodes: list[Node], name: str = "", depth: int = 0
    ) -> dict[str, Any]:
        result: dict[str, Any] = {"type": json_type(value)}
        self.remaining -= 1
        if self.remaining < 0 or depth >= MAX_DEPTH:
            return {**result, "truncated": True}
        if name and sensitive(name):
            result["value"] = REDACTED
            if isinstance(value, (str, list, dict)):
                result["length"] = len(cast(Any, value))
            return result
        if isinstance(value, dict):
            value = cast(dict[str, Any], value)
            known = child_fields(nodes)
            visible: dict[str, Any] = {}
            # Iterate trusted names, not arbitrary caller keys. Work stays bounded
            # even for a request with a large number of unknown extension fields.
            for alias, (canonical, children) in known.items():
                if alias in value and len(visible) < MAX_FIELDS and self.remaining > 0:
                    visible[alias] = self.render(value[alias], children, canonical, depth + 1)
            result["fields"] = visible
            omitted = len(value) - len(visible)
            if omitted:
                result["omitted_fields"] = omitted
            if len(visible) < sum(alias in value for alias in known):
                result["truncated"] = True
        elif isinstance(value, list):
            value = cast(list[Any], value)
            children = [
                Node(get_args(choice.annotation)[0])
                for node in nodes
                for choice in alternatives(node)
                if get_origin(choice.annotation) in (list, tuple) and get_args(choice.annotation)
            ]
            if not children or sensitive(name):
                return {**result, "length": len(value), "value": REDACTED}
            result["items"] = [
                self.render(item, children, name, depth + 1)
                for item in value[:MAX_ITEMS]
                if self.remaining > 0
            ]
            result["length"] = len(value)
            if len(result["items"]) < len(value):
                result["truncated"] = True
        elif isinstance(value, str):
            result["length"] = len(value)
            expects_object = any(
                isinstance(choice.annotation, type) and issubclass(choice.annotation, BaseModel)
                for node in nodes
                for choice in alternatives(node)
            )
            if expects_object:
                # Decode only a logging preview. The original string is forwarded
                # unchanged and must still fail the normal object-type check.
                result["value"] = REDACTED
                if len(value) <= MAX_JSON_STRING:
                    try:
                        decoded = json.loads(value, parse_constant=reject_constant)
                    except (ValueError, RecursionError):
                        result["unparseable_json"] = True
                    else:
                        if isinstance(decoded, dict):
                            result["decoded_preview"] = self.render(decoded, nodes, name, depth + 1)
                else:
                    result["truncated"] = True
            else:
                result["value"] = self.scalar(value, name)
                if len(value) > MAX_STRING:
                    result["truncated"] = True
        else:
            result["value"] = self.scalar(value, name)
        return result


def reject_constant(value: str) -> Any:
    raise ValueError("Non-finite JSON value")


class ToolTrace:
    def __init__(
        self, config: ServerConfig, tool: str | None, model: type[BaseModel] | None
    ) -> None:
        self.enabled = config.server.debug_tool_calls
        self.call_id = ""
        if self.enabled:
            try:
                self.call_id = uuid4().hex
            except Exception:
                self.enabled = False
        self.tool = tool or "[unknown_tool]"
        self.model = model
        self.secrets = (
            (
                config.broker.consumer_key.get_secret_value(),
                config.broker.consumer_secret.get_secret_value(),
                config.server.http_bearer_token.get_secret_value()
                if config.server.http_bearer_token
                else "",
            )
            if self.enabled
            else ()
        )

    def emit(self, event: str, **fields: Any) -> None:
        if not self.enabled:
            return
        try:
            payload = {"event": event, "call_id": self.call_id, "tool": self.tool, **fields}
            line = json.dumps(payload, ensure_ascii=True, allow_nan=False, separators=(",", ":"))
            if len(line.encode("utf-8")) > MAX_EVENT_BYTES:
                payload = {
                    "event": event,
                    "call_id": self.call_id,
                    "tool": self.tool,
                    "truncated": True,
                }
                line = json.dumps(payload, separators=(",", ":"))
            LOGGER.info("%s", line)
        except Exception:
            # No fallback logging: error text and repr() may contain private data.
            pass

    def received(self, arguments: Any) -> None:
        if not self.enabled:
            return
        try:
            preview = ArgumentPreview(self.secrets).render(arguments, [Node(self.model)])
            self.emit("tool_call.received", arguments=preview)
        except Exception:
            self.emit("tool_call.received", preview_unavailable=True)

    def finished(self, result: Any = None, *, outcome: str | None = None) -> None:
        if not self.enabled:
            return
        try:
            details: dict[str, Any] = {}
            if isinstance(result, CallToolResult):
                failed = result.is_error
                content: Any = result.structured_content
            elif isinstance(result, dict):
                # The SDK serializes handler results before returning through
                # middleware; short-circuited boundary results remain models.
                result = cast(dict[str, Any], result)
                failed = result.get("isError", False)
                content = result.get("structuredContent")
            else:
                failed, content = None, None
            if isinstance(failed, bool):
                outcome = "error" if failed else "success"
            if isinstance(content, dict):
                content = cast(dict[str, Any], content)
                error = content.get("error")
                if isinstance(error, dict):
                    error = cast(dict[str, Any], error)
                    code = error.get("code")
                    if isinstance(code, str) and code in get_args(ErrorCode):
                        details["error_code"] = code
                    validations: list[dict[str, Any]] = []
                    raw = error.get("validation_errors", [])
                    for item in cast(list[Any], raw)[:20] if isinstance(raw, list) else []:
                        if isinstance(item, dict):
                            item = cast(dict[str, Any], item)
                            path = item.get("path", [])
                            if not isinstance(path, list):
                                continue
                            path = cast(list[Any], path)
                            if not all(type(part) in (str, int) for part in path):
                                continue
                            location = cast(tuple[str | int, ...], tuple(path[:16]))
                            safe_path, _ = project_path(location, self.model)
                            code = item.get("code")
                            validations.append(
                                {
                                    "path": safe_path,
                                    "code": code
                                    if isinstance(code, str) and code in VALIDATION_CODES
                                    else "invalid_value",
                                }
                            )
                    if validations:
                        details["validation_errors"] = validations
            self.emit("tool_call.completed", outcome=outcome or "completed", **details)
        except Exception:
            self.emit("tool_call.completed", outcome="unknown")
