"""Acceptance gate 5: determinism across PROCESSES.

Findings must sort deterministically regardless of PYTHONHASHSEED (dict/set
iteration order can vary by hash seed unless code is careful never to rely
on it for output ordering -- see rules.py's explicit sort key). We prove
this the honest way: >= 3 real subprocesses, differing PYTHONHASHSEED,
byte-identical stdout.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

from mcpshape import fixtures

REPO_ROOT = Path(__file__).resolve().parents[1]


def _run_cli(manifest_path: Path, hash_seed: str, as_json: bool) -> bytes:
    env = dict(os.environ)
    env["PYTHONHASHSEED"] = hash_seed
    args = [sys.executable, "-m", "mcpshape", str(manifest_path), "--provider", "openai", "--provider", "google"]
    if as_json:
        args.append("--json")
    result = subprocess.run(
        args,
        cwd=str(REPO_ROOT),
        env=env,
        capture_output=True,
        timeout=30,
    )
    return result.stdout


def test_stdout_is_byte_identical_across_hash_seeds(tmp_path):
    manifest, _defects = fixtures.planted_manifest()
    manifest_path = tmp_path / "planted.json"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    seeds = ["0", "1", "12345"]
    for as_json in (False, True):
        outputs = [_run_cli(manifest_path, seed, as_json) for seed in seeds]
        first = outputs[0]
        assert first, "CLI produced no stdout at all"
        for seed, output in zip(seeds[1:], outputs[1:]):
            assert output == first, (
                f"stdout differs between PYTHONHASHSEED runs (as_json={as_json}); "
                f"hash-seed-dependent iteration order leaked into output"
            )
