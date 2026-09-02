"""Unit tests for the stdlib-only default-value validator (rule 8)."""
from __future__ import annotations

from mcpshape.minivalidate import validate_value


def test_valid_value_has_no_violations():
    assert validate_value(5, {"type": "integer", "minimum": 0, "maximum": 10}) == []


def test_type_mismatch_reported():
    violations = validate_value("five", {"type": "integer"})
    assert violations
    assert "type" in violations[0]


def test_minimum_violation_reported():
    violations = validate_value(5, {"type": "integer", "minimum": 10})
    assert any("minimum" in v for v in violations)


def test_enum_violation_reported():
    violations = validate_value("z", {"type": "string", "enum": ["a", "b"]})
    assert any("enum" in v for v in violations)


def test_empty_enum_does_not_itself_crash_validator():
    # rule 8's empty-enum check is separate; the validator must not error.
    assert validate_value("x", {"type": "string", "enum": []}) == []


def test_pattern_violation_reported():
    violations = validate_value("abc", {"type": "string", "pattern": r"^\d+$"})
    assert any("pattern" in v for v in violations)


def test_array_length_bounds():
    assert any("minItems" in v for v in validate_value([], {"type": "array", "minItems": 1}))
    assert any("maxItems" in v for v in validate_value([1, 2, 3], {"type": "array", "maxItems": 2}))


def test_boolean_is_not_treated_as_integer():
    # bool is a subclass of int in Python -- must not pass an integer type check.
    violations = validate_value(True, {"type": "integer"})
    assert violations


def test_integral_float_is_treated_as_integer():
    # JSON Schema draft 2020-12: `integer` accepts any number with a zero
    # fractional part, so a float like 5.0 IS a valid integer.
    assert validate_value(5.0, {"type": "integer"}) == []


def test_large_integral_float_is_treated_as_integer():
    assert validate_value(1e10, {"type": "integer"}) == []


def test_non_integral_float_is_not_treated_as_integer():
    violations = validate_value(5.5, {"type": "integer"})
    assert any("type" in v for v in violations)


def test_boolean_is_not_treated_as_number():
    violations = validate_value(True, {"type": "number"})
    assert violations


def test_integral_and_non_integral_floats_are_treated_as_number():
    assert validate_value(5.0, {"type": "number"}) == []
    assert validate_value(5.5, {"type": "number"}) == []
