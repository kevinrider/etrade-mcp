"""Safe presentation of reported validation failures, never a second validator."""

from __future__ import annotations

import math
import re
import types
from dataclasses import dataclass
from decimal import Decimal
from typing import Annotated, Any, Literal, Union, get_args, get_origin

from pydantic import BaseModel, ConfigDict, Field, ValidateAs, ValidationError
from pydantic.fields import FieldInfo

PathPart = Annotated[str, Field(max_length=64)] | Annotated[int, Field(ge=0, strict=True)]


class ValidationIssue(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, hide_input_in_errors=True)

    path: list[PathPart] = Field(default_factory=list[str | int], max_length=16)
    code: str = Field(min_length=1, max_length=64)
    message: str = Field(min_length=1, max_length=256)


# These messages are owned by the adapter; never return a custom error's msg/ctx.
CUSTOM_MESSAGES = {
    "conflicting_aliases": "Conflicting spellings of a field were supplied. Use one spelling.",
    "decimal_string": 'Use a decimal string, for example "1.25", rather than a JSON number.',
    "nonempty": "Provide a nonempty value.",
    "expiration_format": "Use an expiration in YYYY-MM-DD format.",
    "calendar_date": "Expiration must be a valid calendar date.",
    "whole_contracts": "Option quantities must be whole contracts.",
    "limit_price_required": "This price type requires limit_price.",
    "limit_price_unused": "This price type does not accept limit_price; omit it or use null.",
    "stop_price_required": "This price type requires stop_price.",
    "stop_price_unused": "This price type does not accept stop_price; omit it or use null.",
    "ascending_strikes": "Strikes must strictly increase in the documented leg order.",
    "equal_wing_widths": "Butterfly wings must have equal widths.",
    "distinct_strikes": "Buy and sell strikes must differ.",
}

# Exact matches translate known, static public-client reasons. This table does
# not decide validity, reproduce brokerage rules, or echo unfamiliar messages.
CLIENT_REASONS: dict[str, tuple[str, str]] = {
    "A nonempty value is required": ("nonempty", "Provide a nonempty value."),
    "symbol is required": ("nonempty", "Provide a nonempty symbol."),
    "security_type is required": ("required_security_type", "Provide security_type."),
    "call_put is required for option instruments": (
        "required_call_put",
        "Option instruments require call_put.",
    ),
    "expiration is required for option instruments": (
        "required_expiration",
        "Option instruments require expiration year, month, and day.",
    ),
    "expiration must be a valid calendar date": (
        "calendar_date",
        "Expiration must be a valid calendar date.",
    ),
    "strike_price must be finite and positive for option instruments": (
        "positive_strike",
        "Option strike_price must be finite and greater than zero.",
    ),
    "Quantity values must be finite and positive": (
        "positive_quantity",
        "Quantity must be finite and greater than zero.",
    ),
    "Prices must be finite": ("finite_number", "Prices must be finite."),
    "stop_price must be a decimal value": ("decimal_string", CUSTOM_MESSAGES["decimal_string"]),
    "limit_price is required for limit price types": (
        "limit_price_required",
        "This price type requires limit_price.",
    ),
    "limit_price must be positive": ("positive_price", "limit_price must be greater than zero."),
    "stop_price is required for stop price types": (
        "stop_price_required",
        "This price type requires stop_price.",
    ),
    "stop_price must be positive": ("positive_price", "stop_price must be greater than zero."),
    "limit_price or stop_limit_price is required for STOP_LIMIT": (
        "stop_limit_price_required",
        "STOP_LIMIT requires limit_price or stop_limit_price.",
    ),
    "STOP_LIMIT limit prices must be positive": (
        "positive_price",
        "STOP_LIMIT limit prices must be greater than zero.",
    ),
    "limit_price is not valid for MARKET orders": (
        "limit_price_unused",
        "MARKET orders do not accept limit_price; omit it or use null.",
    ),
    "client_order_id must be 1-20 alphanumeric characters": (
        "client_order_id_format",
        "Use 1–20 ASCII letters or digits for client_order_id.",
    ),
    "At least one instrument is required": (
        "required_instruments",
        "Provide at least one instrument.",
    ),
    "At least one order is required": ("required_orders", "Provide at least one order."),
    "At least one preview ID is required": (
        "required_preview_ids",
        "Provide at least one broker preview ID.",
    ),
    "start_date and end_date must be supplied together": (
        "paired_dates",
        "Supply start_date and end_date together.",
    ),
}
BUILTIN_MESSAGES = {
    "missing": "Field is required.",
    "extra_forbidden": "Unexpected field. Use only the declared fields in this tool's schema.",
    "string_type": "Must be a string.",
    "string_unicode": "Must be valid Unicode text.",
    "int_type": "Must be an integer.",
    "int_parsing": "Must be an integer.",
    "int_from_float": "Must be a whole integer.",
    "float_type": "Must be a number.",
    "float_parsing": "Must be a number.",
    "bool_type": "Must be a boolean.",
    "bool_parsing": "Must be a boolean.",
    "decimal_type": "Must be a decimal string.",
    "decimal_parsing": "Must be a valid decimal string.",
    "finite_number": "Must be finite.",
    "model_type": "Must be an object containing the declared fields.",
    "model_attributes_type": "Must be an object containing the declared fields.",
    "dict_type": "Must be an object.",
    "list_type": "Must be an array.",
    "tuple_type": "Must be an array.",
    "date_parsing": "Must be a valid calendar date.",
}


@dataclass(frozen=True)
class Node:
    annotation: Any
    metadata: tuple[Any, ...] = ()


def alternatives(node: Node) -> list[Node]:
    for index, item in enumerate(node.metadata):
        if isinstance(item, FieldInfo):
            return alternatives(
                Node(
                    node.annotation,
                    (*node.metadata[:index], *item.metadata, *node.metadata[index + 1 :]),
                )
            )
        if isinstance(item, ValidateAs):
            return alternatives(Node(item.from_type))
    origin = get_origin(node.annotation)
    args = get_args(node.annotation)
    if origin is Annotated:
        return alternatives(Node(args[0], (*node.metadata, *args[1:])))
    if origin in (Union, types.UnionType):
        return [choice for arg in args for choice in alternatives(Node(arg, node.metadata))]
    return [node]


def project_path(
    location: tuple[str | int, ...], model: type[BaseModel] | None
) -> tuple[list[str | int], list[Node]]:
    """Walk only public model fields, aliases and array items; stop at unknown keys."""
    path: list[str | int] = []
    nodes = [Node(model)]
    for part in location:
        nodes = [choice for node in nodes for choice in alternatives(node)]
        matches: list[Node] = []
        canonical: str | int | None = None
        for node in nodes:
            annotation = node.annotation
            if (
                isinstance(part, str)
                and isinstance(annotation, type)
                and issubclass(annotation, BaseModel)
            ):
                for name, field in annotation.model_fields.items():
                    if part in (name, field.alias, field.validation_alias):
                        canonical = name
                        matches.append(Node(field.annotation, tuple(field.metadata)))
            elif type(part) is int and part >= 0 and get_origin(annotation) in (list, tuple):
                args = get_args(annotation)
                if args:
                    canonical = part
                    matches.append(Node(args[0]))
        if canonical is None or not matches or len(path) >= 16:
            break
        if isinstance(canonical, str) and len(canonical) > 64:
            break
        path.append(canonical)
        nodes = matches
    return path, [choice for node in nodes for choice in alternatives(node)]


def constraint(nodes: list[Node], name: str) -> str | None:
    for node in nodes:
        for metadata in node.metadata:
            value = getattr(metadata, name, None)
            if isinstance(value, bool) or not isinstance(value, (int, float, Decimal)):
                continue
            if isinstance(value, float) and not math.isfinite(value):
                continue
            if isinstance(value, Decimal) and not value.is_finite():
                continue
            # Keep even trusted metadata small; never serialize arbitrary context.
            if isinstance(value, int) and value.bit_length() > 100:
                continue
            text = str(value)
            if len(text) <= 32:
                return text
    return None


def choices_message(nodes: list[Node]) -> str:
    values = [
        value
        for node in nodes
        if get_origin(node.annotation) is Literal
        for value in get_args(node.annotation)
        if isinstance(value, (str, int))
    ]
    if values:
        message = "Must be one of: " + ", ".join(str(value) for value in values) + "."
        if len(message) <= 256:
            return message
    return "Use an allowed choice from this field's schema or description."


def translate(kind: str, raw_message: str, nodes: list[Node]) -> tuple[str, str]:
    if kind in CUSTOM_MESSAGES:
        return kind, CUSTOM_MESSAGES[kind]
    if kind in BUILTIN_MESSAGES:
        return kind, BUILTIN_MESSAGES[kind]
    if kind == "literal_error":
        return kind, choices_message(nodes)
    for code, metadata_name, wording in (
        ("greater_than", "gt", "Must be greater than"),
        ("greater_than_equal", "ge", "Must be at least"),
        ("less_than", "lt", "Must be less than"),
        ("less_than_equal", "le", "Must be at most"),
        ("string_too_short", "min_length", "Minimum length is"),
        ("string_too_long", "max_length", "Maximum length is"),
        ("too_short", "min_length", "Minimum number of items is"),
        ("too_long", "max_length", "Maximum number of items is"),
    ):
        if kind == code:
            bound = constraint(nodes, metadata_name)
            return (
                kind,
                f"{wording} {bound}."
                if bound is not None
                else "Check this field's declared bounds.",
            )
    if kind == "string_pattern_mismatch":
        return kind, "Use the format declared in this field's schema."
    if kind == "value_error":
        reason = raw_message.removeprefix("Value error, ")
        if reason in CLIENT_REASONS:
            return CLIENT_REASONS[reason]
        # Match only the reason's structure. Choices/labels from exception text
        # are never reflected; model metadata is the only source of suggestions.
        if re.fullmatch(r"[a-z_]+ must be one of: [A-Z0-9_, ]+", reason) or reason in {
            "Unsupported quote detail flag",
            "Unsupported option expiration type",
            "Unsupported option category",
            "Unsupported chain type",
            "Unsupported price type",
            "Unsupported alert category",
            "Unsupported alert status",
        }:
            return "unsupported_choice", choices_message(nodes)
    return "invalid_value", "Value does not satisfy the declared constraints."


def validation_diagnostics(
    error: Exception, model: type[BaseModel] | None = None, *, client: bool = False
) -> list[ValidationIssue]:
    """Project reported errors; neither validate inputs again nor expose exception details."""
    underlying: BaseException | None = error
    visited: set[int] = set()
    for _ in range(8):
        if (
            underlying is None
            or id(underlying) in visited
            or isinstance(underlying, ValidationError)
        ):
            break
        visited.add(id(underlying))
        underlying = underlying.__cause__
    if isinstance(underlying, ValidationError):
        details = underlying.errors(include_input=False, include_context=False, include_url=False)
        issues: list[ValidationIssue] = []
        seen: set[tuple[tuple[str | int, ...], str, str]] = set()
        for detail in details:
            location = detail["loc"]
            path, nodes = project_path(location, model)
            if client and model is not None and "request" in model.model_fields:
                nested_path, nested_nodes = project_path(("request", *location), model)
                if len(nested_path) > len(path):
                    path, nodes = nested_path, nested_nodes
            code, message = translate(detail["type"], detail["msg"], nodes)
            key = (tuple(path), code, message)
            if key in seen:
                continue
            seen.add(key)
            if len(issues) == 20:
                issues[-1] = ValidationIssue(
                    code="additional_errors", message="Further validation errors were omitted."
                )
                break
            issues.append(ValidationIssue(path=path, code=code, message=message))
        return issues or [
            ValidationIssue(
                code="invalid_value", message="Check the declared fields and constraints."
            )
        ]
    # Plain public-client validation errors have no structured locations. Only
    # recognized exact reasons may supply guidance; arbitrary text stays private.
    reason = str(error)
    if reason in CLIENT_REASONS:
        code, message = CLIENT_REASONS[reason]
        hint = "symbol" if reason == "symbol is required" else ""
        path, _ = project_path((hint,), model)
        if not path and hint and model is not None and "symbols" in model.model_fields:
            path.append("symbols")
        return [ValidationIssue(path=path, code=code, message=message)]
    if model is not None:
        for name in model.model_fields:
            if reason == f"{name} is required":
                return [
                    ValidationIssue(
                        path=[name], code="nonempty", message="Provide a nonempty value."
                    )
                ]
            if reason == f"{name} must be a positive integer":
                return [
                    ValidationIssue(
                        path=[name], code="positive_integer", message="Provide a positive integer."
                    )
                ]
    return [
        ValidationIssue(
            code="invalid_value",
            message="Request failed validation; check the declared fields and constraints.",
        )
    ]
