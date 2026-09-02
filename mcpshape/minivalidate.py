"""Minimal, mechanical JSON-Schema-subset validator.

We deliberately do not depend on the `jsonschema` package (zero
runtime deps, stdlib only). This module checks exactly what rule 8 needs:
does a `default` value satisfy the local subschema it sits inside? This is
pure structural validation -- type, enum membership, numeric bounds, string
length/pattern, array length -- never a judgement about meaning.

Not a general-purpose validator: unknown/unhandled keywords are silently
not checked (they don't make a default "invalid" by omission -- rule 1
separately flags unsupported keywords). This keeps the surface small and
auditable.
"""
from __future__ import annotations

import re
from typing import Any


def _is_integer_typed(v: Any) -> bool:
    """JSON Schema draft 2020-12: `integer` matches any JSON number with a
    zero fractional part, not just values that happen to be Python `int`.
    A `float` like `5.0` is a valid integer; `5.5` is not. `bool` is never
    a JSON number/integer even though Python's `bool` subclasses `int`.
    """
    if isinstance(v, bool):
        return False
    if isinstance(v, int):
        return True
    if isinstance(v, float):
        return v.is_integer()
    return False


_TYPE_CHECKERS = {
    "string": lambda v: isinstance(v, str),
    "number": lambda v: isinstance(v, (int, float)) and not isinstance(v, bool),
    "integer": _is_integer_typed,
    "boolean": lambda v: isinstance(v, bool),
    "object": lambda v: isinstance(v, dict),
    "array": lambda v: isinstance(v, list),
    "null": lambda v: v is None,
}


def validate_value(value: Any, schema: dict) -> list[str]:
    """Return a list of human-readable violation strings (empty == valid)."""
    violations: list[str] = []
    if not isinstance(schema, dict):
        return violations

    declared_type = schema.get("type")
    if isinstance(declared_type, str):
        checker = _TYPE_CHECKERS.get(declared_type)
        if checker is not None and not checker(value):
            violations.append(f"type: expected {declared_type}, got {_typename(value)}")
    elif isinstance(declared_type, list):
        if not any(_TYPE_CHECKERS.get(t, lambda v: False)(value) for t in declared_type):
            violations.append(f"type: expected one of {declared_type}, got {_typename(value)}")

    enum = schema.get("enum")
    if isinstance(enum, list) and len(enum) > 0 and value not in enum:
        violations.append(f"enum: {value!r} not in {enum!r}")

    if isinstance(value, str):
        pattern = schema.get("pattern")
        if isinstance(pattern, str):
            try:
                if re.search(pattern, value) is None:
                    violations.append(f"pattern: {value!r} does not match {pattern!r}")
            except re.error:
                pass  # malformed pattern is not this validator's concern
        min_len = schema.get("minLength")
        if isinstance(min_len, int) and len(value) < min_len:
            violations.append(f"minLength: len({value!r})={len(value)} < {min_len}")
        max_len = schema.get("maxLength")
        if isinstance(max_len, int) and len(value) > max_len:
            violations.append(f"maxLength: len({value!r})={len(value)} > {max_len}")

    if isinstance(value, (int, float)) and not isinstance(value, bool):
        minimum = schema.get("minimum")
        if isinstance(minimum, (int, float)) and value < minimum:
            violations.append(f"minimum: {value} < {minimum}")
        maximum = schema.get("maximum")
        if isinstance(maximum, (int, float)) and value > maximum:
            violations.append(f"maximum: {value} > {maximum}")
        exclusive_min = schema.get("exclusiveMinimum")
        if isinstance(exclusive_min, (int, float)) and value <= exclusive_min:
            violations.append(f"exclusiveMinimum: {value} <= {exclusive_min}")
        exclusive_max = schema.get("exclusiveMaximum")
        if isinstance(exclusive_max, (int, float)) and value >= exclusive_max:
            violations.append(f"exclusiveMaximum: {value} >= {exclusive_max}")

    if isinstance(value, list):
        min_items = schema.get("minItems")
        if isinstance(min_items, int) and len(value) < min_items:
            violations.append(f"minItems: len={len(value)} < {min_items}")
        max_items = schema.get("maxItems")
        if isinstance(max_items, int) and len(value) > max_items:
            violations.append(f"maxItems: len={len(value)} > {max_items}")

    return violations


def _typename(value: Any) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, int):
        return "integer"
    if isinstance(value, float):
        return "number"
    if isinstance(value, str):
        return "string"
    if isinstance(value, list):
        return "array"
    if isinstance(value, dict):
        return "object"
    return type(value).__name__
