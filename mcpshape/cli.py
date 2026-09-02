"""mcpshape command-line entry point.

Design choices, each a deliberate default:

* `--provider NAME` may be repeated to lint against several providers in one
  pass. If omitted entirely, mcpshape lints against
  `providers.DEFAULT_PROVIDER_SET` (openai, anthropic, google) -- useful
  output with zero config on the very first run, per the "zero-friction
  first run" goal.
* An explicitly-named provider not in the table is not silently skipped: it
  produces `unknown-provider` findings (see rules.py) so the exit code
  reflects "could not evaluate this", never "clean".
* Exit codes: 0 clean, 1 findings (including unknown-provider verdicts --
  an unknown verdict is explicitly NOT "clean"), 2 malformed
  input / unusable manifest.
"""
from __future__ import annotations

import argparse
import json
import sys
from typing import Sequence

from . import __version__
from .ingest import ManifestError, parse_text
from .providers import DEFAULT_PROVIDER_SET, PROVIDERS, get as get_provider
from .rules import lint

EXIT_CLEAN = 0
EXIT_FINDINGS = 1
EXIT_MALFORMED = 2


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="mcpshape",
        description="Lint an MCP server's tools/list output against per-provider "
        "tool-calling compatibility tables. No network, no NL judgement -- "
        "structural JSON Schema checks only.",
    )
    parser.add_argument(
        "manifest",
        nargs="?",
        default=None,
        help="path to a tools/list JSON file (default: read from stdin)",
    )
    parser.add_argument(
        "--provider",
        action="append",
        dest="providers",
        metavar="NAME",
        help=f"provider to lint against (repeatable). Known: {', '.join(sorted(PROVIDERS))}. "
        f"Default when omitted: {', '.join(DEFAULT_PROVIDER_SET)}.",
    )
    parser.add_argument("--json", action="store_true", help="emit machine-readable JSON instead of text")
    parser.add_argument("--version", action="version", version=f"mcpshape {__version__}")
    return parser


def _read_input(manifest_path: str | None) -> str:
    if manifest_path is None or manifest_path == "-":
        return sys.stdin.read()
    with open(manifest_path, "r", encoding="utf-8") as fh:
        return fh.read()


def _severity_counts(findings: list[dict]) -> dict[str, int]:
    counts = {"error": 0, "unknown": 0}
    for f in findings:
        counts[f["severity"]] = counts.get(f["severity"], 0) + 1
    return counts


def _render_text(findings: list[dict], tool_count: int, providers_run: Sequence[str]) -> str:
    counts = _severity_counts(findings)
    lines = []
    if not findings:
        lines.append(
            f"mcpshape: {tool_count} tool(s) checked against [{', '.join(providers_run)}] -- 0 findings, clean."
        )
        return "\n".join(lines) + "\n"

    lines.append(
        f"mcpshape: {tool_count} tool(s) checked against [{', '.join(providers_run)}] -- "
        f"{len(findings)} finding(s): {counts['error']} error, {counts['unknown']} unknown."
    )
    lines.append("")
    lines.append(f"{'tool_name':<28}{'rule_id':<28}{'json_pointer':<40}message")
    lines.append("-" * 110)
    for f in findings:
        tool_name = str(f["tool_name"])
        lines.append(f"{tool_name:<28.28}{f['rule_id']:<28}{f['json_pointer']:<40}{f['message']}")
    return "\n".join(lines) + "\n"


def _resolve_provider_tables(requested: Sequence[str]) -> dict[str, object]:
    return {key: get_provider(key) for key in requested}


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        raw_text = _read_input(args.manifest)
    except OSError as exc:
        sys.stderr.write(f"mcpshape: cannot read input: {exc}\n")
        return EXIT_MALFORMED

    try:
        parsed = parse_text(raw_text)
    except RecursionError as exc:  # belt-and-braces: never a raw traceback
        diagnostic = f"input nests too deeply to parse: {exc.__class__.__name__}"
        if args.json:
            sys.stdout.write(json.dumps({"error": diagnostic}, sort_keys=True) + "\n")
        else:
            sys.stderr.write(f"mcpshape: malformed input: {diagnostic}\n")
        return EXIT_MALFORMED
    except ManifestError as exc:
        if args.json:
            sys.stdout.write(json.dumps({"error": str(exc)}, sort_keys=True) + "\n")
        else:
            sys.stderr.write(f"mcpshape: malformed input: {exc}\n")
        return EXIT_MALFORMED

    providers_run = list(args.providers) if args.providers else list(DEFAULT_PROVIDER_SET)
    provider_tables = _resolve_provider_tables(providers_run)

    # Defense-in-depth backstop (the crash-surface rule): the walk itself
    # (schemawalk.walk) is the primary fix for unbounded-depth input -- it is
    # iterative (explicit stack, no Python recursion), so it cannot exhaust
    # the call stack no matter how deep the input nests, and it has no
    # depth cap of its own (a cap there would silently drop findings deeper
    # than the cap -- fail-unsafe; see schemawalk.py). This try/except is
    # only a last-resort net so that ANY *other* unexpected exception during
    # linting still produces a clean exit 2 with a one-line diagnostic on
    # stderr (and, under --json, still-valid JSON on stdout) instead of a
    # raw traceback and empty stdout.
    try:
        findings = lint(parsed.tools, parsed.tools_root, provider_tables)
    except Exception as exc:  # noqa: BLE001 - intentional last-resort backstop
        diagnostic = f"internal error while linting: {exc.__class__.__name__}: {exc}"
        if args.json:
            sys.stdout.write(json.dumps({"error": diagnostic}, sort_keys=True) + "\n")
        else:
            sys.stderr.write(f"mcpshape: {diagnostic}\n")
        return EXIT_MALFORMED

    if args.json:
        payload = {
            "tool_count": len(parsed.tools),
            "providers": providers_run,
            "finding_count": len(findings),
            "findings": findings,
        }
        sys.stdout.write(json.dumps(payload, sort_keys=True, indent=2) + "\n")
    else:
        sys.stdout.write(_render_text(findings, len(parsed.tools), providers_run))

    return EXIT_CLEAN if not findings else EXIT_FINDINGS


if __name__ == "__main__":
    sys.exit(main())
