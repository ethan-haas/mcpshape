"""Parse a `tools/list`-shaped manifest into a normalized tool list.

Accepted top-level shapes:
  1. {"tools": [...]}
  2. {"result": {"tools": [...]}}
  3. [...]                       (bare array of tool objects)

We never mutate or re-shape the document itself -- callers keep the raw
parsed document around so that JSON Pointers built by rules.py resolve
against exactly what was supplied. This module's job is only to figure out
*where* the tools array lives (the "tools root pointer") and to validate
each tool minimally enough to either proceed or fail with exit code 2.
"""
from __future__ import annotations

import json
from dataclasses import dataclass


class ManifestError(Exception):
    """Raised for anything that makes the manifest unusable (exit code 2)."""


@dataclass
class ParsedManifest:
    document: object          # the raw parsed JSON, untouched
    tools_root: str           # JSON Pointer prefix to the tools array, e.g. "/tools"
    tools: list[dict]         # the tool objects themselves (== document at tools_root)


def parse_text(raw_text: str) -> ParsedManifest:
    """Parse a tools/list document, turning every unusable input into a
    ManifestError the CLI can report as a clean exit 2.

    RecursionError is caught alongside JSONDecodeError on purpose. On CPython
    3.11 and earlier the stdlib JSON *decoder* exhausts the C call stack on a
    deeply nested document and raises RecursionError, which is not a
    JSONDecodeError -- so before this it escaped as a raw traceback with empty
    stdout, breaking both the crash-surface rule and the --json contract, and
    it did so only on <=3.11 (3.12 raised the interpreter's recursion
    handling, which is why the same input is fine on newer runtimes).

    The linter's own walk is iterative and cannot recurse (see schemawalk),
    but that fix covered only half the class: input this deep never reaches
    the walk, because json.loads dies first. Depth this extreme is not
    something to lint -- it is malformed input, and it is reported as such.
    """
    try:
        document = json.loads(raw_text)
    except json.JSONDecodeError as exc:
        raise ManifestError(f"input is not valid JSON: {exc}") from exc
    except RecursionError as exc:
        raise ManifestError(
            "input nests too deeply for this interpreter's JSON decoder to "
            "parse (RecursionError). The document is structurally too deep to "
            "be a usable tool manifest; treat it as malformed input"
        ) from exc
    return parse_document(document)


def parse_document(document: object) -> ParsedManifest:
    if isinstance(document, list):
        tools_root = ""
        tools = document
    elif isinstance(document, dict) and isinstance(document.get("tools"), list):
        tools_root = "/tools"
        tools = document["tools"]
    elif (
        isinstance(document, dict)
        and isinstance(document.get("result"), dict)
        and isinstance(document["result"].get("tools"), list)
    ):
        tools_root = "/result/tools"
        tools = document["result"]["tools"]
    else:
        raise ManifestError(
            "document is not a recognized tools/list shape: expected a bare "
            'array, {"tools": [...]}, or {"result": {"tools": [...]}}'
        )

    for idx, tool in enumerate(tools):
        if not isinstance(tool, dict):
            raise ManifestError(f"tool at index {idx} is not a JSON object")
        name = tool.get("name")
        if not isinstance(name, str) or name == "":
            raise ManifestError(f"tool at index {idx} is missing a non-empty 'name'")

    return ParsedManifest(document=document, tools_root=tools_root, tools=tools)
