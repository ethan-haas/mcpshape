"""Unit tests for the RFC 6901 pointer helpers."""
from __future__ import annotations

from mcpshape import pointer as ptr


def test_join_and_resolve_round_trip():
    doc = {"tools": [{"name": "a", "inputSchema": {"type": "object"}}]}
    pointer = ptr.join("", "tools", 0, "name")
    assert pointer == "/tools/0/name"
    found, value = ptr.resolve(doc, pointer)
    assert found is True
    assert value == "a"


def test_resolve_empty_pointer_is_whole_document():
    doc = {"x": 1}
    found, value = ptr.resolve(doc, "")
    assert found is True
    assert value is doc


def test_resolve_missing_key_not_found():
    doc = {"tools": []}
    found, _value = ptr.resolve(doc, "/tools/0")
    assert found is False


def test_escape_and_unescape_tilde_and_slash():
    assert ptr.escape_token("a/b~c") == "a~1b~0c"
    assert ptr.unescape_token("a~1b~0c") == "a/b~c"
    doc = {"weird/key~name": 42}
    pointer = ptr.join("", "weird/key~name")
    found, value = ptr.resolve(doc, pointer)
    assert found is True
    assert value == 42


def test_leading_zero_index_is_invalid():
    doc = [1, 2, 3]
    found, _value = ptr.resolve(doc, "/01")
    assert found is False
