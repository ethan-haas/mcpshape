"""Acceptance gate 6: the linter can go red.

Positive control -- mutate (silence) a rule the way a real regression
would, and prove the corresponding planted-defect assertion in
test_planted.py would then fail. This is the "self-mutant panel" check:
it demonstrates the gate is not an inert probe that always reports 0
findings regardless of what runs through it.
"""
from __future__ import annotations

from mcpshape import fixtures, rules
from tests.conftest import default_provider_tables


def test_silencing_a_rule_makes_its_planted_defect_undetectable(monkeypatch):
    manifest, defects = fixtures.planted_manifest()
    tables = default_provider_tables()

    target = next(d for d in defects if d.rule_id == rules.RULE_UNSUPPORTED_KEYWORD)

    # Before mutation: the check has teeth.
    findings_before = rules.lint(manifest["tools"], "/tools", tables)
    assert any(
        f["rule_id"] == target.rule_id and f["tool_name"] == target.tool_name
        for f in findings_before
    )

    # Mutate: replace the check with a no-op, simulating a silenced rule
    # (e.g. someone accidentally guts the keyword-scan loop in a refactor).
    monkeypatch.setitem(
        rules.PROVIDER_DEPENDENT_CHECKS,
        rules.RULE_UNSUPPORTED_KEYWORD,
        lambda tool, tool_ptr, table: [],
    )

    findings_after = rules.lint(manifest["tools"], "/tools", tables)
    assert not any(
        f["rule_id"] == target.rule_id and f["tool_name"] == target.tool_name
        for f in findings_after
    ), "mutated rule still fired -- the mutation didn't actually silence it, so this is not a valid positive control"

    # This is exactly the regression test_planted.py's
    # test_every_planted_defect_class_is_detected would catch for real: if
    # RULE_UNSUPPORTED_KEYWORD's check were genuinely silenced (not just
    # monkeypatched here), that test goes red on the next run.
