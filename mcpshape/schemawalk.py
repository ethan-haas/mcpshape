"""Structural walk over a JSON Schema tree (mechanical, no NL).

Yields every schema node reachable from an inputSchema, together with the
JSON Pointer to that node (relative to the tool's inputSchema) and its
containment "depth" (root = 1, +1 each time we cross into a nested
object/array-typed property or items schema). Used by rules 1, 2, 6, 8.
"""
from __future__ import annotations

from typing import Iterator

from . import pointer as ptr

NESTING_TYPES = ("object", "array")

# NOTE on the r1 crash fix vs. this r2 fix:
#
# r1 made `walk` iterative (explicit stack instead of Python recursion) to
# eliminate RecursionError on deeply-nested input. That alone is sufficient:
# an iterative walk consumes zero additional Python call frames per schema
# level, so it cannot stack-overflow at ANY depth -- there is nothing here
# for a physical-descent cap to protect against.
#
# r1 ALSO added a hard `MAX_WALK_DEPTH = 40` cap that silently stopped
# descending into a branch (without yielding its descendants) once physical
# descent passed 40 steps. That was a SEPARATE, unjustified change bundled
# into the crash fix, and it was fail-unsafe: any finding whose node sits
# deeper than 40 structural steps (via properties/items/allOf/anyOf/etc.)
# was never visited, so rules 1, 2, 5, 6, 7, 8, 9 could never see it and the
# linter would exit 0 "clean" on a manifest that contains a real, reachable
# defect. A crash-safety fix must never trade a crash for a silent false
# negative -- so the cap is removed here. `walk` now visits every node
# reachable from the schema, at any depth, exactly as the pre-r1 recursive
# version did semantically (just without recursion). The input is already
# bounded by what `json.loads` parsed off stdin, so there is no unbounded
# work here that json.loads itself didn't already do.


def is_object_node(schema: dict) -> bool:
    """Best-effort structural detection of an object schema node.

    Explicit `"type": "object"` always counts. A schema that declares
    `properties` but omits `type` is also treated as an object -- common in
    the wild, and rule 6 (additionalProperties) needs to catch it too.
    """
    if not isinstance(schema, dict):
        return False
    if schema.get("type") == "object":
        return True
    return "type" not in schema and isinstance(schema.get("properties"), dict)


def walk(schema: object, base_pointer: str, depth: int = 1) -> Iterator[tuple[str, dict, int]]:
    """Yield (pointer, node, depth) for `schema` and every descendant schema node.

    Iterative (explicit stack), not recursive: no input -- however deeply
    nested -- can exhaust the Python call stack here. Traversal order is
    pre-order depth-first, same as the old recursive-descent version. There
    is no depth cap: every reachable node is visited and yielded, so every
    rule that consumes this generator sees every finding regardless of how
    deep it sits (see module docstring for why a cap here would be
    fail-unsafe). `depth` is the *logical* object/array-nesting depth that
    rule 2 (nesting-too-deep) compares against each provider's documented
    cap -- that check happens in rules.py against the yielded `depth`, not
    by this function refusing to descend.
    """
    if not isinstance(schema, dict):
        return

    # Stack entries: (node, node_pointer, logical_depth).
    stack: list[tuple[dict, str, int]] = [(schema, base_pointer, depth)]
    while stack:
        node, node_ptr, node_depth = stack.pop()
        yield node_ptr, node, node_depth

        children: list[tuple[dict, str, int]] = []

        props = node.get("properties")
        if isinstance(props, dict):
            for name, sub in props.items():
                if isinstance(sub, dict):
                    child_depth = node_depth + 1 if sub.get("type") in NESTING_TYPES else node_depth
                    children.append((sub, ptr.join(node_ptr, "properties", name), child_depth))

        items = node.get("items")
        if isinstance(items, dict):
            child_depth = node_depth + 1 if items.get("type") in NESTING_TYPES else node_depth
            children.append((items, ptr.join(node_ptr, "items"), child_depth))
        elif isinstance(items, list):
            for i, sub in enumerate(items):
                if isinstance(sub, dict):
                    child_depth = node_depth + 1 if sub.get("type") in NESTING_TYPES else node_depth
                    children.append((sub, ptr.join(node_ptr, "items", i), child_depth))

        pattern_props = node.get("patternProperties")
        if isinstance(pattern_props, dict):
            for pat, sub in pattern_props.items():
                if isinstance(sub, dict):
                    children.append((sub, ptr.join(node_ptr, "patternProperties", pat), node_depth))

        addl = node.get("additionalProperties")
        if isinstance(addl, dict):
            children.append((addl, ptr.join(node_ptr, "additionalProperties"), node_depth))

        for combinator in ("oneOf", "anyOf", "allOf"):
            lst = node.get(combinator)
            if isinstance(lst, list):
                for i, sub in enumerate(lst):
                    if isinstance(sub, dict):
                        children.append((sub, ptr.join(node_ptr, combinator, i), node_depth))

        not_sub = node.get("not")
        if isinstance(not_sub, dict):
            children.append((not_sub, ptr.join(node_ptr, "not"), node_depth))

        for kw in ("if", "then", "else"):
            sub = node.get(kw)
            if isinstance(sub, dict):
                children.append((sub, ptr.join(node_ptr, kw), node_depth))

        # Push in reverse so popping preserves the original left-to-right,
        # pre-order depth-first yield order of the recursive version.
        for child_schema, child_ptr, child_depth in reversed(children):
            stack.append((child_schema, child_ptr, child_depth))
