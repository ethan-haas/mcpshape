"""Regression test for the r1-fix-introduced fail-unsafe truncation escape.

r1 (the RecursionError crash fix) bundled in a second, unrelated change:
`schemawalk.MAX_WALK_DEPTH = 40`, a hard cap on *physical* descent that made
`walk()` silently stop visiting -- and therefore silently stop *reporting on*
-- any branch more than 40 structural steps below a tool's inputSchema root.
Every provider-independent rule that walks the schema tree (5
required-missing-property, 8 empty-enum-or-bad-default) never even saw a
defect buried past that depth, so mcpshape exited 0 "clean" on a manifest
that contains a real, reachable defect -- the exact fail-unsafe direction
the design forbids. (Rule 7 duplicate-tool-name and rule 9
missing-input-schema do not call schemawalk.walk at all -- they inspect the
tool list / the tool dict directly, not schema-tree nodes -- so they were
never subject to this escape; they are not exercised here for that reason.)

Confirmed repro (see the task spec) buried an empty-enum defect 40 `allOf`
levels deep: pre-fix, finding_count was 0 and exit was 0; post-fix it must
be 1 (empty-enum-or-bad-default) and exit 1.

This file drives the real CLI via subprocess, matching test_deep_nesting.py,
so it observes the exact same crash-surface/exit-code contract a real
invocation would.
"""
from __future__ import annotations

import json
import subprocess
import sys

import pytest

DEPTHS = (2, 45, 100, 300)  # 2 is the shallow control; the others sit well
# past the old MAX_WALK_DEPTH=40 cap and must behave identically to depth 2.


def _run_cli(manifest_text: str, args: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-m", "mcpshape", *args],
        input=manifest_text,
        capture_output=True,
        text=True,
        timeout=60,
    )


def _assert_clean_crash_surface(result: subprocess.CompletedProcess) -> None:
    assert "Traceback" not in result.stderr, f"raw traceback leaked to stderr:\n{result.stderr}"
    assert result.returncode in (0, 1, 2), f"unexpected exit code {result.returncode}"
    assert result.stdout != "", "stdout must not be empty under --json"
    json.loads(result.stdout)  # must parse -- raises if not valid JSON


# ---------------------------------------------------------------------------
# Burial mechanisms: wrap a leaf defect `depth` structural steps below the
# root via each of the three ways schemawalk.walk descends without
# incrementing *logical* nesting depth (properties/items DO increment
# logical depth when the child is object/array-typed; allOf never does --
# the confirmed repro deliberately used allOf so the old cap fired well
# before rule 2's own per-provider nesting cap ever could).
# ---------------------------------------------------------------------------


def _bury_via_properties(leaf: dict, depth: int) -> dict:
    node = leaf
    for _ in range(depth):
        node = {"type": "object", "properties": {"k": node}}
    return node


def _bury_via_items(leaf: dict, depth: int) -> dict:
    node = leaf
    for _ in range(depth):
        node = {"type": "array", "items": node}
    return node


def _bury_via_allof(leaf: dict, depth: int) -> dict:
    node = leaf
    for _ in range(depth):
        node = {"allOf": [node]}
    return node


BURIAL_MECHANISMS = {
    "properties": _bury_via_properties,
    "items": _bury_via_items,
    "allOf": _bury_via_allof,
}


# ---------------------------------------------------------------------------
# Leaf defects, one per buriable provider-independent rule.
# ---------------------------------------------------------------------------


def _leaf_empty_enum() -> dict:
    return {"type": "string", "enum": []}


def _leaf_bad_default() -> dict:
    # declared type "string" but default is an int -- violates its own
    # local schema (minivalidate.validate_value type check).
    return {"type": "string", "default": 123}


def _leaf_required_missing_property() -> dict:
    return {"type": "object", "properties": {}, "required": ["ghost"]}


LEAF_DEFECTS = {
    "empty-enum-or-bad-default": _leaf_empty_enum,
    "bad-default": _leaf_bad_default,
    "required-missing-property": _leaf_required_missing_property,
}

EXPECTED_RULE_ID = {
    "empty-enum-or-bad-default": "empty-enum-or-bad-default",
    "bad-default": "empty-enum-or-bad-default",  # same rule, different trigger
    "required-missing-property": "required-missing-property",
}


def _wrap_in_manifest(buried_schema: dict, tool_name: str = "t") -> dict:
    # Wrap the buried leaf under a top-level object schema so rule 9
    # (missing-input-schema) doesn't fire and add noise; the property key
    # "x" adds one more properties-hop, which is irrelevant to the assertion
    # (we only check the target rule_id is present with a resolving pointer,
    # not that it's the *only* finding).
    schema = {"type": "object", "properties": {"x": buried_schema}, "additionalProperties": True}
    return {"tools": [{"name": tool_name, "description": "d", "inputSchema": schema}]}


@pytest.mark.parametrize("mechanism_name", sorted(BURIAL_MECHANISMS))
@pytest.mark.parametrize("defect_name", sorted(LEAF_DEFECTS))
@pytest.mark.parametrize("depth", DEPTHS)
def test_buried_defect_still_reported(depth, defect_name, mechanism_name):
    leaf = LEAF_DEFECTS[defect_name]()
    bury = BURIAL_MECHANISMS[mechanism_name]
    buried = bury(leaf, depth)
    manifest = _wrap_in_manifest(buried)

    result = _run_cli(json.dumps(manifest), ["--provider", "anthropic", "--json"])
    _assert_clean_crash_surface(result)

    payload = json.loads(result.stdout)
    expected_rule_id = EXPECTED_RULE_ID[defect_name]
    matches = [f for f in payload["findings"] if f["rule_id"] == expected_rule_id]
    assert matches, (
        f"expected a '{expected_rule_id}' finding at depth={depth} "
        f"buried via {mechanism_name!r}; got none. finding_count="
        f"{payload['finding_count']}, rule_ids="
        f"{sorted({f['rule_id'] for f in payload['findings']})}"
    )

    found, _value = _resolve_pointer(manifest, matches[0]["json_pointer"])
    assert found, (
        f"json_pointer {matches[0]['json_pointer']!r} does not resolve in "
        f"the supplied manifest (depth={depth}, mechanism={mechanism_name})"
    )
    assert result.returncode == 1, (
        f"expected exit 1 (findings present) at depth={depth} via "
        f"{mechanism_name!r}, got {result.returncode}"
    )


def _resolve_pointer(document, pointer: str):
    from mcpshape import pointer as ptr

    return ptr.resolve(document, pointer)


# ---------------------------------------------------------------------------
# duplicate-tool-name: explicitly NOT buriable via schemawalk depth -- it is
# a same-index scan over the tools list, independent of schema-tree shape.
# Included here only as documentation that it was considered and found N/A.
# ---------------------------------------------------------------------------


def test_duplicate_tool_name_is_not_schemawalk_dependent():
    # Two tools with identical names must still be flagged regardless of how
    # deeply-nested (or not) their schemas are -- proving this rule was
    # never exposed to the MAX_WALK_DEPTH escape in the first place, since
    # check_duplicate_tool_name never calls schemawalk.walk.
    deep_schema = _bury_via_allof({"type": "string"}, 300)
    manifest = {
        "tools": [
            {"name": "dup", "description": "d", "inputSchema": {"type": "object", "properties": {"x": deep_schema}}},
            {"name": "dup", "description": "d", "inputSchema": {"type": "object", "properties": {}}},
        ]
    }
    result = _run_cli(json.dumps(manifest), ["--provider", "anthropic", "--json"])
    _assert_clean_crash_surface(result)
    payload = json.loads(result.stdout)
    rule_ids = {f["rule_id"] for f in payload["findings"]}
    assert "duplicate-tool-name" in rule_ids
    assert result.returncode == 1


# ---------------------------------------------------------------------------
# Unknown provider (--provider bogus): the provider-dependent checks can't
# run (no table to check against), but the provider-*independent* protocol
# checks (5, 8) still run unconditionally in rules.lint -- a deep structural
# defect must still be reported even when every requested provider is
# unknown.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("mechanism_name", sorted(BURIAL_MECHANISMS))
@pytest.mark.parametrize("defect_name", sorted(LEAF_DEFECTS))
def test_unknown_provider_still_reports_deep_structural_defect(defect_name, mechanism_name):
    leaf = LEAF_DEFECTS[defect_name]()
    bury = BURIAL_MECHANISMS[mechanism_name]
    buried = bury(leaf, 100)
    manifest = _wrap_in_manifest(buried)

    result = _run_cli(json.dumps(manifest), ["--provider", "bogus", "--json"])
    _assert_clean_crash_surface(result)

    payload = json.loads(result.stdout)
    rule_ids = {f["rule_id"] for f in payload["findings"]}
    assert "unknown-provider" in rule_ids
    expected_rule_id = EXPECTED_RULE_ID[defect_name]
    assert expected_rule_id in rule_ids, (
        f"deep structural defect ({expected_rule_id}) not reported under "
        f"an unknown provider; rule_ids={sorted(rule_ids)}"
    )
    assert result.returncode == 1
