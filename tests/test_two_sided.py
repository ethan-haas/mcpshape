"""Acceptance gate 2: two-sided evaluation, reported separately, never blended.

detection_rate: fraction of planted defect classes caught (test_planted.py
proves each is caught at least once; here we compute the rate over
individual planted tool instances for the metric report).
false_flag_rate: fraction of tools in the VALID corpus that produce at
least one finding. Must be exactly 0.0 -- a linter that flags every
schema fails this gate.
"""
from __future__ import annotations

from mcpshape import fixtures, rules
from tests.conftest import default_provider_tables


def test_valid_manifest_produces_zero_findings():
    manifest = fixtures.valid_manifest()
    findings = rules.lint(manifest["tools"], "/tools", default_provider_tables())
    assert findings == [], f"valid manifest should be clean, got: {findings}"


def test_detection_rate_and_false_flag_rate_reported_separately():
    valid = fixtures.valid_manifest()
    planted, defects = fixtures.planted_manifest()

    tables = default_provider_tables()
    valid_findings = rules.lint(valid["tools"], "/tools", tables)
    planted_findings = rules.lint(planted["tools"], "/tools", tables)

    flagged_valid_tools = {f["tool_name"] for f in valid_findings}
    false_flag_rate = len(flagged_valid_tools) / len(valid["tools"])

    detected_rule_ids = {(f["rule_id"], f["tool_name"]) for f in planted_findings}
    caught = sum(1 for d in defects if (d.rule_id, d.tool_name) in detected_rule_ids)
    detection_rate = caught / len(defects)

    # Never averaged/blended into one number -- asserted independently.
    assert false_flag_rate == 0.0, f"false_flag_rate={false_flag_rate}, expected 0.0"
    assert detection_rate == 1.0, f"detection_rate={detection_rate}, expected 1.0"
