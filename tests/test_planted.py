"""Acceptance gate 1: every planted defect class is detected.

Each planted tool must produce at least one finding whose rule_id matches
the class planted, whose tool_name matches, and whose json_pointer
resolves inside the exact document supplied to lint().
"""
from __future__ import annotations

from mcpshape import fixtures, rules
from tests.conftest import default_provider_tables, pointer_resolves


def test_every_planted_defect_class_is_detected():
    manifest, defects = fixtures.planted_manifest()
    findings = rules.lint(manifest["tools"], "/tools", default_provider_tables())

    assert defects, "fixture generator produced no planted defects"
    for defect in defects:
        matches = [
            f
            for f in findings
            if f["rule_id"] == defect.rule_id and f["tool_name"] == defect.tool_name
        ]
        assert matches, (
            f"expected a '{defect.rule_id}' finding for tool "
            f"'{defect.tool_name}' ({defect.note}); got none. "
            f"All findings for that tool: "
            f"{[f for f in findings if f['tool_name'] == defect.tool_name]}"
        )
        for f in matches:
            assert pointer_resolves(manifest, f["json_pointer"]), (
                f"json_pointer {f['json_pointer']!r} for rule "
                f"{f['rule_id']!r} does not resolve in the supplied document"
            )


def test_every_rule_id_is_reachable_by_at_least_one_planted_defect():
    _manifest, defects = fixtures.planted_manifest()
    planted_rule_ids = {d.rule_id for d in defects}
    # rules.py's 9 spec rule_ids (unknown-provider is a separate fail-safe
    # verdict, not one of the 9, and is covered by test_tables.py instead).
    nine_rule_ids = set(rules.PROVIDER_DEPENDENT_RULE_IDS) | set(rules.PROTOCOL_RULE_IDS)
    missing = nine_rule_ids - planted_rule_ids
    assert not missing, f"planted corpus has no coverage for rule(s): {missing}"
