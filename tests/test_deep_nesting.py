"""Regression test for the RecursionError crash escape.

A deeply-but-validly-nested JSON manifest used to drive schemawalk.walk's
plain recursive descent (and pointer.join's f-string building on top of it)
past CPython's default recursion limit (~1000 frames). The CLI then raised
an uncaught RecursionError: traceback on stderr, EMPTY stdout, exit 1 --
violating both the crash-surface rule (no traceback / clean 0/1/2
only) and the --json contract (stdout must always parse as JSON).

This test drives the real CLI via subprocess (not in-process cli.main())
deliberately: an in-process pytest call already has frames on the stack and
may not reproduce the exact stack-exhaustion condition a fresh interpreter
process hits, and a subprocess also proves stdout/stderr behave the way a
real invocation would (buffering, flush-on-exit, etc). Depths below (~1200)
are chosen because they crashed the pre-fix code (see the task's confirmed
repro) and comfortably exceed every provider's documented
max_nesting_depth (<=8, providers.py). schemawalk.walk itself has no depth
cap (see schemawalk.py) -- a cap there would silently drop findings deeper
than it, which is a separate, fail-unsafe bug covered by
test_deep_defect_reported.py; this file only exercises the no-crash
behavior (and that the nesting-too-deep finding itself is not truncated
away) at extreme depth.
"""
from __future__ import annotations

import json
import subprocess
import sys

# Deep enough to violate every provider's cap (all <= 8) by two orders of
# magnitude, but shallow enough that EVERY supported interpreter's stdlib JSON
# decoder can still parse it. CPython 3.11 and earlier exhaust the C stack
# decoding a document thousands of levels deep, at which point the correct
# behaviour is "malformed input, exit 2" and no finding exists to assert --
# so a findings test pinned to that depth would encode a 3.12+-only
# expectation. PATHOLOGICAL_DEPTH below covers that case separately.
DEPTH = 200

# Deliberately past what CPython <= 3.11 can decode at all. Used only for the
# crash-surface property, which must hold on every version: whatever the
# interpreter does, mcpshape must not emit a traceback and must not break the
# --json contract.
PATHOLOGICAL_DEPTH = 1200




def _manifest_text(schema_text: str, name: str = "t") -> str:
    """Build the manifest as TEXT, never via json.dumps().

    Encoding a 1200-deep object with the stdlib encoder raises RecursionError
    on CPython 3.11 and earlier, so a test that built its input that way could
    not even run there -- it failed in its own setup, before the CLI was
    invoked, and reported nothing about the behaviour it exists to check.
    Assembling the JSON as a string sidesteps the encoder entirely, so this
    regression runs on every supported interpreter.
    """
    return ('{"tools":[{"name":"' + name + '","description":"d","inputSchema":'
            + schema_text + "}]}")


def _deep_object_text(depth: int) -> str:
    node = '{"type":"string"}'
    for _ in range(depth):
        node = '{"type":"object","additionalProperties":false,"properties":{"k":' + node + "}}"
    return node


def _deep_array_text(depth: int) -> str:
    node = '{"type":"string"}'
    for _ in range(depth):
        node = '{"type":"array","items":' + node + "}"
    return node


def _run_cli(manifest_text: str, args: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-m", "mcpshape", *args],
        input=manifest_text,
        capture_output=True,
        text=True,
        timeout=60,
    )


def _assert_clean_crash_surface(result: subprocess.CompletedProcess, json_mode: bool) -> None:
    assert "Traceback" not in result.stderr, f"raw traceback leaked to stderr:\n{result.stderr}"
    assert "RecursionError" not in result.stderr, f"RecursionError leaked to stderr:\n{result.stderr}"
    assert result.returncode in (0, 1, 2), f"unexpected exit code {result.returncode}"
    if json_mode:
        assert result.stdout != "", "stdout must not be empty under --json"
        json.loads(result.stdout)  # must parse -- raises if not valid JSON


def test_deep_object_nesting_openai_json_reports_nesting_too_deep():
    result = _run_cli(_manifest_text(_deep_object_text(DEPTH)), ["--provider", "openai", "--json"])
    _assert_clean_crash_surface(result, json_mode=True)

    payload = json.loads(result.stdout)
    rule_ids = {f["rule_id"] for f in payload["findings"]}
    assert "nesting-too-deep" in rule_ids


def test_deep_array_items_nesting_json():
    schema_text = '{"type":"object","properties":{"a":' + _deep_array_text(DEPTH) + "}}"
    result = _run_cli(_manifest_text(schema_text, name="t2"), ["--provider", "anthropic", "--json"])
    _assert_clean_crash_surface(result, json_mode=True)

    payload = json.loads(result.stdout)
    rule_ids = {f["rule_id"] for f in payload["findings"]}
    assert "nesting-too-deep" in rule_ids


def test_deep_object_nesting_default_provider_set_json():
    # No --provider flag: exercises DEFAULT_PROVIDER_SET (openai, anthropic,
    # google) -- i.e. the walk runs multiple times per tool, once per
    # provider-dependent check per provider.
    result = _run_cli(_manifest_text(_deep_object_text(DEPTH), name="t3"), ["--json"])
    _assert_clean_crash_surface(result, json_mode=True)

    payload = json.loads(result.stdout)
    providers_with_nesting_finding = {
        f["provider"] for f in payload["findings"] if f["rule_id"] == "nesting-too-deep"
    }
    # google (max 4), openai (max 5), anthropic (max 8) all sit well below
    # DEPTH -- every default provider must still detect the violation.
    assert providers_with_nesting_finding == {"openai", "anthropic", "google"}


def test_deep_object_nesting_bare_array_shape_json():
    # Bare-array top-level manifest shape (no "tools" wrapper).
    bare = '[{"name":"t4","description":"d","inputSchema":' + _deep_object_text(DEPTH) + "}]"
    result = _run_cli(bare, ["--provider", "openai", "--json"])
    _assert_clean_crash_surface(result, json_mode=True)

    payload = json.loads(result.stdout)
    rule_ids = {f["rule_id"] for f in payload["findings"]}
    assert "nesting-too-deep" in rule_ids


def test_deep_object_nesting_text_mode_no_traceback():
    # Non-JSON text mode: no --json contract to satisfy, but the
    # no-traceback / clean-exit-code crash-surface rule still applies.
    result = _run_cli(_manifest_text(_deep_object_text(DEPTH), name="t5"), ["--provider", "openai"])
    _assert_clean_crash_surface(result, json_mode=False)
    assert "nesting-too-deep" in result.stdout


def test_shallow_valid_schema_still_clean():
    # Control: a schema well within every provider's cap must still lint
    # clean (or at least crash-free) after switching walk() to iterative --
    # no regression in ordinary, non-adversarial behavior.
    schema = {
        "type": "object",
        "additionalProperties": False,
        "properties": {"a": {"type": "object", "additionalProperties": False, "properties": {"b": {"type": "string"}}}},
    }
    manifest = {"tools": [{"name": "shallow", "description": "d", "inputSchema": schema}]}
    result = _run_cli(json.dumps(manifest), ["--provider", "openai", "--json"])
    _assert_clean_crash_surface(result, json_mode=True)
    payload = json.loads(result.stdout)
    rule_ids = {f["rule_id"] for f in payload["findings"]}
    assert "nesting-too-deep" not in rule_ids


def test_pathologically_deep_input_never_crashes_on_any_interpreter():
    """Depth past what older interpreters can decode at all.

    Two outcomes are both correct, and which one you get depends on the
    running interpreter, not on mcpshape: on CPython 3.12+ the document parses
    and the nesting violation is reported (exit 1); on 3.11 and earlier the
    stdlib decoder cannot build it, which is malformed input (exit 2). This
    test therefore asserts only the property that must hold either way --
    no traceback, a documented exit code, and valid JSON on stdout under
    --json. Asserting a specific verdict here would pin the suite to one
    interpreter's stack limits.
    """
    result = _run_cli(
        _manifest_text(_deep_object_text(PATHOLOGICAL_DEPTH), name="pathological"),
        ["--provider", "openai", "--json"],
    )
    _assert_clean_crash_surface(result, json_mode=True)
    assert result.returncode in (1, 2), result.returncode
