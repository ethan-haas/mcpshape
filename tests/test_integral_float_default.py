"""Regression: `type: integer` must accept an integral-valued JSON number
(a float with zero fractional part), per JSON Schema draft 2020-12 (the
draft MCP's `inputSchema` uses). Before the fix, mcpshape's default-value
validator (rule 8, empty-enum-or-bad-default) rejected e.g. `5.0` against
`{"type": "integer"}` -- a false-positive escape found by independent
audit. The canonical `jsonschema` package accepts `validate(5.0,
{"type": "integer"})`; mcpshape must too.

These are full-process CLI runs (subprocess, `python -m mcpshape`) so the
regression is proven end to end, not just at the validator-function level
(see tests/test_minivalidate.py for the unit-level companion).
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]


def _manifest(schema_extra: dict, default) -> dict:
    return {
        "tools": [
            {
                "name": "t",
                "description": "d",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "n": {**schema_extra, "default": default},
                    },
                    "additionalProperties": False,
                },
            }
        ]
    }


def _run(manifest: dict) -> tuple[int, dict]:
    result = subprocess.run(
        [sys.executable, "-m", "mcpshape", "--provider", "openai", "--json"],
        cwd=str(REPO_ROOT),
        input=json.dumps(manifest).encode("utf-8"),
        capture_output=True,
        timeout=30,
    )
    payload = json.loads(result.stdout)
    return result.returncode, payload


def _rule_ids(payload: dict) -> list[str]:
    return [f["rule_id"] for f in payload["findings"]]


# --- must be CLEAN: integral-valued floats ARE valid JSON-Schema integers ---


def test_integral_float_default_is_clean():
    code, payload = _run(_manifest({"type": "integer"}, 5.0))
    assert code == 0, payload
    assert payload["finding_count"] == 0
    assert "empty-enum-or-bad-default" not in _rule_ids(payload)


def test_large_integral_float_default_is_clean():
    code, payload = _run(_manifest({"type": "integer"}, 1e10))
    assert code == 0, payload
    assert payload["finding_count"] == 0


def test_integral_float_default_within_enum_is_clean():
    code, payload = _run(_manifest({"type": "integer", "enum": [1, 2, 3]}, 2.0))
    assert code == 0, payload
    assert payload["finding_count"] == 0


def test_number_type_integral_float_default_is_clean():
    code, payload = _run(_manifest({"type": "number"}, 5.0))
    assert code == 0, payload
    assert payload["finding_count"] == 0


def test_number_type_non_integral_float_default_is_clean():
    code, payload = _run(_manifest({"type": "number"}, 5.5))
    assert code == 0, payload
    assert payload["finding_count"] == 0


def test_integral_float_default_with_multiple_of_five_stays_clean():
    # multipleOf is not an implemented keyword in mcpshape's stdlib-only
    # validator (unhandled keywords are silently not checked -- see
    # minivalidate.py docstring); this proves the type-predicate fix does
    # not regress a schema that also carries an unrelated keyword.
    code, payload = _run(_manifest({"type": "integer", "multipleOf": 5}, 10.0))
    assert code == 0, payload
    assert payload["finding_count"] == 0


# --- must still FLAG: these are genuine violations, not the false positive ---


def test_non_integral_float_default_still_flags():
    code, payload = _run(_manifest({"type": "integer"}, 5.5))
    assert code == 1
    assert "empty-enum-or-bad-default" in _rule_ids(payload)
    violations = payload["findings"][0]["evidence"]["violations"]
    assert any("type" in v and "integer" in v for v in violations)


def test_bool_default_still_flags_against_integer_type():
    # Python bool is a subclass of int but is NOT a JSON integer/number.
    code, payload = _run(_manifest({"type": "integer"}, True))
    assert code == 1
    assert "empty-enum-or-bad-default" in _rule_ids(payload)
    violations = payload["findings"][0]["evidence"]["violations"]
    assert any("boolean" in v for v in violations)


def test_bool_default_still_flags_against_number_type():
    code, payload = _run(_manifest({"type": "number"}, True))
    assert code == 1
    assert "empty-enum-or-bad-default" in _rule_ids(payload)
