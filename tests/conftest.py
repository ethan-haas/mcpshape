"""Shared test helpers."""
from __future__ import annotations

from mcpshape import pointer as ptr
from mcpshape import providers


def default_provider_tables():
    return {key: providers.get(key) for key in providers.DEFAULT_PROVIDER_SET}


def pointer_resolves(document, json_pointer: str) -> bool:
    found, _value = ptr.resolve(document, json_pointer)
    return found
