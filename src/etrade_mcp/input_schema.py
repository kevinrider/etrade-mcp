"""Inline discovery schemas without changing runtime models or validation."""

from __future__ import annotations

from copy import deepcopy
from typing import Any, cast
from urllib.parse import unquote

_SCHEMA_MAPS = frozenset(
    {"properties", "patternProperties", "dependentSchemas", "$defs", "definitions", "dependencies"}
)
_SCHEMA_ARRAYS = frozenset({"allOf", "anyOf", "oneOf", "prefixItems"})
_SCHEMA_VALUES = frozenset(
    {
        "additionalProperties",
        "additionalItems",
        "unevaluatedProperties",
        "unevaluatedItems",
        "contains",
        "propertyNames",
        "not",
        "if",
        "then",
        "else",
        "contentSchema",
    }
)
_ANNOTATIONS = frozenset(
    {
        "title",
        "description",
        "default",
        "examples",
        "deprecated",
        "readOnly",
        "writeOnly",
        "$comment",
    }
)


def _combine(target: Any, siblings: dict[str, Any]) -> Any:
    """Reference siblings constrain the target; they must not overwrite its rules."""
    if target is False:
        return {**siblings, "allOf": [False, *siblings.get("allOf", [])]}
    if target is True:
        return siblings
    target = cast(dict[str, Any], target)
    if siblings.keys() - _ANNOTATIONS:
        annotations = {
            key: value for key, value in {**target, **siblings}.items() if key in _ANNOTATIONS
        }
        return {
            **annotations,
            **siblings,
            # Keep reference-site constraints outside the target's scope so
            # unevaluatedProperties/items can see the reference annotations.
            "allOf": [target, *siblings.get("allOf", [])],
        }
    return {**target, **siblings}


def inline_input_schema(schema: dict[str, Any]) -> dict[str, Any]:
    """Expand root-local JSON Pointers; retain cycles and other reference forms.

    Only schema-bearing keywords are traversed. Literal defaults, enums, and
    examples may themselves contain keys named $ref and must remain untouched.
    """
    root = deepcopy(schema)
    retained_reference = False

    def resolve(reference: str) -> Any:
        pointer = unquote(reference[1:])
        value: Any = root
        try:
            for escaped in pointer.split("/")[1:] if pointer else []:
                key = escaped.replace("~1", "/").replace("~0", "~")
                if isinstance(value, dict):
                    value = cast(dict[str, Any], value)[key]
                elif isinstance(value, list) and key.isascii() and key.isdecimal():
                    value = cast(list[Any], value)[int(key)]
                else:
                    raise ValueError
        except (KeyError, IndexError, ValueError):
            raise ValueError("Input schema contains an unresolved local reference.") from None
        if not isinstance(value, (dict, bool)):
            raise ValueError("Input schema reference does not target a schema.")
        return cast(dict[str, Any] | bool, value)

    def expand(node: Any, active: tuple[str, ...] = ()) -> Any:
        nonlocal retained_reference
        if not isinstance(node, dict):
            return deepcopy(node)
        node = cast(dict[str, Any], node)
        # These keywords establish reference scopes beyond root-local pointers.
        # Preserve such subtrees rather than resolve their references incorrectly.
        if any(key in node for key in ("$id", "$dynamicRef", "$recursiveRef")):
            retained_reference = True
            return deepcopy(node)
        result: dict[str, Any] = {}
        for key, value in node.items():
            if key in _SCHEMA_MAPS and isinstance(value, dict):
                result[key] = {
                    name: expand(child, active)
                    for name, child in cast(dict[str, Any], value).items()
                }
            elif (key in _SCHEMA_ARRAYS or key == "items") and isinstance(value, list):
                result[key] = [expand(child, active) for child in cast(list[Any], value)]
            elif key in _SCHEMA_VALUES or key == "items":
                result[key] = expand(value, active)
            else:
                result[key] = deepcopy(value)
        reference = node.get("$ref")
        if reference is None:
            return result
        if not isinstance(reference, str):
            raise ValueError("Input schema reference must be a string.")
        if reference != "#" and not reference.startswith("#/"):
            retained_reference = True
            return result
        target = resolve(reference)
        if reference in active or (
            isinstance(target, dict) and "$id" in cast(dict[str, Any], target)
        ):
            retained_reference = True
            return result
        siblings = {key: value for key, value in result.items() if key != "$ref"}
        return _combine(expand(target, (*active, reference)), siblings)

    body = {key: value for key, value in root.items() if key != "$defs"}
    expanded = expand(body)
    if isinstance(expanded, dict):
        result = cast(dict[str, Any], expanded)
    else:
        result = {"allOf": [expanded]}
    if retained_reference and "$defs" in root:
        result["$defs"] = deepcopy(root["$defs"])
    return result
