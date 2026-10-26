"""Discovery inlining preserves JSON Schema behavior and literal user data."""

from copy import deepcopy
from typing import Any, Protocol, cast

import pytest
from jsonschema import Draft202012Validator

from etrade_mcp.input_schema import inline_input_schema


class SchemaValidator(Protocol):
    def is_valid(self, instance: object) -> bool: ...


def equivalent(schema: dict[str, Any], values: list[Any]) -> dict[str, Any]:
    before = deepcopy(schema)
    inlined = inline_input_schema(schema)
    assert schema == before
    Draft202012Validator.check_schema(inlined)
    original = cast(SchemaValidator, Draft202012Validator(schema))
    expanded = cast(SchemaValidator, Draft202012Validator(inlined))
    for value in values:
        assert original.is_valid(value) == expanded.is_valid(value), value
    return inlined


def test_nested_definitions_annotations_and_independent_copies() -> None:
    schema: dict[str, Any] = {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "first": {"$ref": "#/$defs/Item", "description": "First item"},
            "second": {"$ref": "#/$defs/Item"},
        },
        "required": ["first"],
        "$defs": {
            "Item": {
                "type": "object",
                "description": "Shared item",
                "additionalProperties": False,
                "properties": {"amount": {"$ref": "#/$defs/Amount"}},
                "required": ["amount"],
            },
            "Amount": {"type": "string", "pattern": "^[0-9]+$", "default": "1"},
        },
    }
    inlined = equivalent(
        schema,
        [
            {"first": {"amount": "12"}},
            {"first": {"amount": 12}},
            {"first": {"amount": "bad"}},
            {"first": {}},
            {},
            {"first": {"amount": "1", "extra": True}},
        ],
    )
    assert inlined == {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "first": {
                "type": "object",
                "description": "First item",
                "additionalProperties": False,
                "properties": {"amount": {"type": "string", "pattern": "^[0-9]+$", "default": "1"}},
                "required": ["amount"],
            },
            "second": {
                "type": "object",
                "description": "Shared item",
                "additionalProperties": False,
                "properties": {"amount": {"type": "string", "pattern": "^[0-9]+$", "default": "1"}},
                "required": ["amount"],
            },
        },
        "required": ["first"],
    }
    inlined["properties"]["first"]["properties"]["amount"]["default"] = "2"
    assert inlined["properties"]["second"]["properties"]["amount"]["default"] == "1"
    assert schema["$defs"]["Amount"]["default"] == "1"


def test_arrays_unions_nullable_and_conditional_schemas() -> None:
    schema: dict[str, Any] = {
        "type": "array",
        "minItems": 1,
        "prefixItems": [{"$ref": "#/$defs/Code"}],
        "items": {"anyOf": [{"$ref": "#/$defs/Code"}, {"type": "null"}]},
        "contains": {"$ref": "#/$defs/Code"},
        "allOf": [{"if": {"minItems": 3}, "then": {"maxItems": 3}, "else": {"maxItems": 2}}],
        "$defs": {"Code": {"type": "string", "enum": ["A", "B"]}},
    }
    inlined = equivalent(schema, [["A"], ["B", None], [None], ["C"], ["A", 1], [], ["A"] * 4])
    assert "$defs" not in inlined
    assert inlined["prefixItems"] == [{"type": "string", "enum": ["A", "B"]}]
    assert inlined["items"]["anyOf"][0] == inlined["prefixItems"][0]


@pytest.mark.parametrize("target", [True, False, {"type": "integer", "minimum": 1}])
def test_reference_sibling_constraints_are_conjunctive(target: Any) -> None:
    schema: dict[str, Any] = {
        "$ref": "#/$defs/Value",
        "description": "Local description",
        "maximum": 5,
        "allOf": [{"not": {"const": 3}}],
        "$defs": {"Value": target},
    }
    inlined = equivalent(schema, [None, "text", 0, 1, 3, 5, 6, True])
    assert inlined["description"] == "Local description"
    assert "$defs" not in inlined


def test_overlapping_properties_and_unevaluated_constraints_keep_their_scope() -> None:
    schema: dict[str, Any] = {
        "$ref": "#/$defs/Record",
        "properties": {"b": {"type": "integer"}},
        "unevaluatedProperties": False,
        "$defs": {"Record": {"type": "object", "properties": {"a": {"type": "string"}}}},
    }
    inlined = equivalent(schema, [{}, {"a": "x"}, {"a": "x", "b": 2}, {"a": 2}, {"c": True}])
    assert inlined["unevaluatedProperties"] is False
    schema["$defs"]["Record"]["unevaluatedProperties"] = False
    schema.pop("unevaluatedProperties")
    equivalent(schema, [{}, {"a": "x"}, {"b": 2}, {"a": "x", "b": 2}])


def test_literals_and_schema_property_names_are_not_references() -> None:
    literal = {"$ref": "#/$defs/Missing", "$defs": {"Literal": "data"}}
    schema: dict[str, Any] = {
        "type": "object",
        "properties": {
            "$ref": {"type": "string"},
            "payload": {
                "type": "object",
                "default": literal,
                "examples": [literal],
                "enum": [literal],
            },
        },
        "examples": [{"payload": literal}],
    }
    inlined = equivalent(schema, [{"$ref": "text"}, {"payload": literal}, {"payload": {}}])
    assert inlined == schema and inlined is not schema


@pytest.mark.parametrize("mutual", [False, True])
def test_recursive_references_retain_original_definitions(mutual: bool) -> None:
    node = {
        "type": "object",
        "required": ["value"],
        "properties": {
            "value": {"type": "integer"},
            "next": {
                "anyOf": [{"$ref": "#/$defs/Link" if mutual else "#/$defs/Node"}, {"type": "null"}]
            },
        },
    }
    definitions: dict[str, Any] = {"Node": node}
    if mutual:
        definitions["Link"] = {"$ref": "#/$defs/Node"}
    schema = {"$ref": "#/$defs/Node", "$defs": definitions}
    inlined = equivalent(
        schema,
        [
            {"value": 1},
            {"value": 1, "next": None},
            {"value": 1, "next": {"value": 2}},
            {"value": 1, "next": {"value": "bad"}},
            {},
        ],
    )
    assert inlined["$defs"] == definitions
    assert inlined["type"] == "object"


@pytest.mark.parametrize("reference", ["https://example.invalid/schema", "#anchor"])
def test_non_pointer_references_are_retained_without_networking(reference: str) -> None:
    schema = {"$ref": reference, "$defs": {"Unused": {"type": "string"}}}
    assert inline_input_schema(schema) == schema


def test_nested_resource_scopes_are_preserved() -> None:
    resource = {
        "$id": "https://example.invalid/resource",
        "$ref": "#/$defs/Local",
        "$defs": {"Local": {"type": "string"}},
    }
    schema: dict[str, Any] = {
        "properties": {"value": {"$ref": "#/$defs/Resource"}},
        "$defs": {"Resource": resource},
    }
    assert inline_input_schema(schema) == schema
    assert inline_input_schema(resource) == resource
    dynamic = {"$dynamicRef": "#node", "$defs": {"Value": {"type": "string"}}}
    assert inline_input_schema(dynamic) == dynamic


@pytest.mark.parametrize("reference", ["#/$defs/a~1b~0c", "#/$defs/a%7E1b%7E0c"])
def test_json_pointer_escaping(reference: str) -> None:
    schema = {"$ref": reference, "$defs": {"a/b~c": {"type": "string"}}}
    assert equivalent(schema, ["x", 1, None]) == {"type": "string"}


@pytest.mark.parametrize(
    "reference",
    [
        "#/$defs/Missing",
        "#/$defs/NotASchema",
        "#/$defs/Items/8",
        "#/$defs/Items/bad",
        "#/$defs/NotASchema/child",
        1,
    ],
)
def test_invalid_local_references_fail_visibly(reference: Any) -> None:
    schema = {"$ref": reference, "$defs": {"NotASchema": "literal", "Items": [{"type": "string"}]}}
    with pytest.raises(ValueError, match="Input schema"):
        inline_input_schema(schema)


def test_json_pointer_array_target_and_boolean_root() -> None:
    assert inline_input_schema(
        {"$ref": "#/$defs/Values/0", "$defs": {"Values": [{"type": "string"}]}}
    ) == {"type": "string"}
    for target in (True, False):
        schema = {"$ref": "#/$defs/Value", "$defs": {"Value": target}}
        equivalent(schema, [None, "x", {}, 1])
