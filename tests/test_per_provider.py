"""Acceptance gate 3: per-provider correctness is its own gate.

A schema legal for one provider and illegal for a stricter one must be
reported for the stricter provider and SILENT for the permissive one. This
is the over-rejection control: a fix that lands on half its class would
either miss the illegal case or wrongly flag the legal one.
"""
from __future__ import annotations

from mcpshape import fixtures, providers, rules
from tests.conftest import pointer_resolves


def test_legal_for_one_provider_silent_illegal_for_another_reported():
    manifest, expectation = fixtures.per_provider_manifest()

    legal_table = {expectation["legal_provider"]: providers.get(expectation["legal_provider"])}
    illegal_table = {expectation["illegal_provider"]: providers.get(expectation["illegal_provider"])}

    legal_findings = rules.lint(manifest["tools"], "/tools", legal_table)
    illegal_findings = rules.lint(manifest["tools"], "/tools", illegal_table)

    legal_rule_hits = [f for f in legal_findings if f["rule_id"] == expectation["rule_id"]]
    illegal_rule_hits = [f for f in illegal_findings if f["rule_id"] == expectation["rule_id"]]

    assert legal_rule_hits == [], (
        f"{expectation['legal_provider']} should be SILENT for this schema, "
        f"got: {legal_rule_hits}"
    )
    assert illegal_rule_hits, (
        f"{expectation['illegal_provider']} should report '{expectation['rule_id']}' "
        "for this schema, got nothing"
    )
    for f in illegal_rule_hits:
        assert pointer_resolves(manifest, f["json_pointer"])
        assert f["tool_name"] == expectation["tool_name"]
