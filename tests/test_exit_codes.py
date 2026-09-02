"""Acceptance: CLI exit codes 0 (clean) / 1 (findings) / 2 (malformed)."""
from __future__ import annotations

import io
import json
import sys

from mcpshape import cli, fixtures


def test_exit_0_on_clean_manifest(tmp_path):
    manifest = fixtures.valid_manifest()
    p = tmp_path / "clean.json"
    p.write_text(json.dumps(manifest), encoding="utf-8")
    assert cli.main([str(p), "--provider", "openai"]) == cli.EXIT_CLEAN


def test_exit_1_on_findings(tmp_path):
    manifest, _defects = fixtures.planted_manifest()
    p = tmp_path / "planted.json"
    p.write_text(json.dumps(manifest), encoding="utf-8")
    assert cli.main([str(p), "--provider", "openai"]) == cli.EXIT_FINDINGS


def test_exit_2_on_invalid_json(tmp_path):
    p = tmp_path / "bad.json"
    p.write_text("{not valid json", encoding="utf-8")
    assert cli.main([str(p)]) == cli.EXIT_MALFORMED


def test_exit_2_on_not_a_tools_list(tmp_path):
    p = tmp_path / "wrong_shape.json"
    p.write_text(json.dumps({"nope": []}), encoding="utf-8")
    assert cli.main([str(p)]) == cli.EXIT_MALFORMED


def test_exit_2_on_tool_missing_name(tmp_path):
    p = tmp_path / "no_name.json"
    p.write_text(json.dumps({"tools": [{"description": "no name field"}]}), encoding="utf-8")
    assert cli.main([str(p)]) == cli.EXIT_MALFORMED


def test_stdin_used_when_no_path_given(monkeypatch, tmp_path):
    manifest = fixtures.valid_manifest()
    monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps(manifest)))
    assert cli.main(["--provider", "openai"]) == cli.EXIT_CLEAN


def test_json_output_is_valid_json_and_reports_finding_count(tmp_path, capsys):
    manifest, _defects = fixtures.planted_manifest()
    p = tmp_path / "planted.json"
    p.write_text(json.dumps(manifest), encoding="utf-8")
    code = cli.main([str(p), "--provider", "openai", "--json"])
    out = capsys.readouterr().out
    payload = json.loads(out)
    assert code == cli.EXIT_FINDINGS
    assert payload["finding_count"] == len(payload["findings"])
    assert payload["finding_count"] > 0
