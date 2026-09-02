"""RFC 6901 JSON Pointer helpers.

Every finding this linter emits carries a json_pointer. The contract (see
"Verdict contract") is that the pointer MUST resolve inside the document the
caller actually supplied -- not some internally-normalized copy. These
helpers build pointers with correct escaping and can resolve a pointer back
against a document, which the test suite uses to prove every finding's
pointer is real.
"""
from __future__ import annotations

from typing import Any


def escape_token(token: str) -> str:
    """Escape one reference-token per RFC 6901 (~ -> ~0, / -> ~1)."""
    return token.replace("~", "~0").replace("/", "~1")


def unescape_token(token: str) -> str:
    return token.replace("~1", "/").replace("~0", "~")


def join(prefix: str, *tokens: object) -> str:
    """Append one or more raw (unescaped) tokens to a pointer prefix.

    `join("", "tools", 0, "name")` -> "/tools/0/name"
    `join("/tools/0")` -> "/tools/0" (no-op, useful for pointing at a whole node)
    """
    parts = [prefix] if prefix else [""]
    out = prefix
    for t in tokens:
        out += "/" + escape_token(str(t))
    return out


def resolve(document: Any, pointer: str) -> tuple[bool, Any]:
    """Resolve an RFC 6901 pointer against `document`.

    Returns (found, value). The empty string resolves to the whole document
    (found=True). Malformed pointers (not starting with "/", when non-empty)
    resolve to (False, None).
    """
    if pointer == "":
        return True, document
    if not pointer.startswith("/"):
        return False, None
    node = document
    for raw_token in pointer.split("/")[1:]:
        token = unescape_token(raw_token)
        if isinstance(node, dict):
            if token not in node:
                return False, None
            node = node[token]
        elif isinstance(node, list):
            if token == "-" or not _is_index(token):
                return False, None
            idx = int(token)
            if idx < 0 or idx >= len(node):
                return False, None
            node = node[idx]
        else:
            return False, None
    return True, node


def _is_index(token: str) -> bool:
    if token == "":
        return False
    if token != "0" and token.startswith("0"):
        return False  # leading zeros are not valid array indices per RFC 6901
    return token.isdigit()
