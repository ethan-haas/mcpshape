"""The 9 mechanical rules plus the unknown-provider fail-safe.

Every rule is a pure function over already-parsed JSON: a tool dict, its
JSON Pointer, and (for provider-dependent rules) a `ProviderTable`. Nothing
here reads a description's meaning -- only structural facts: lengths,
regex matches against a name string, schema-tree shape, and set membership
of JSON Schema keywords.

Finding shape (the verdict contract):
    {rule_id, severity, tool_name, json_pointer, provider, evidence, message}

`provider` is the provider key for provider-dependent rules, or the literal
string "-" for provider-independent protocol rules (5, 7, 8, 9), which do
not vary by provider and are only ever run once per lint pass.
"""
from __future__ import annotations

from typing import Iterable

from . import pointer as ptr
from . import schemawalk
from .minivalidate import validate_value
from .providers import ProviderTable

PROTOCOL = "-"  # provider field for provider-independent findings

RULE_UNSUPPORTED_KEYWORD = "unsupported-keyword"
RULE_NESTING_TOO_DEEP = "nesting-too-deep"
RULE_NAME_PATTERN = "name-pattern"
RULE_DESCRIPTION_TOO_LONG = "description-too-long"
RULE_REQUIRED_MISSING_PROPERTY = "required-missing-property"
RULE_ADDITIONAL_PROPERTIES_OPEN = "additional-properties-open"
RULE_DUPLICATE_TOOL_NAME = "duplicate-tool-name"
RULE_EMPTY_ENUM_OR_BAD_DEFAULT = "empty-enum-or-bad-default"
RULE_MISSING_INPUT_SCHEMA = "missing-input-schema"
RULE_UNKNOWN_PROVIDER = "unknown-provider"

PROVIDER_DEPENDENT_RULE_IDS = (
    RULE_UNSUPPORTED_KEYWORD,
    RULE_NESTING_TOO_DEEP,
    RULE_NAME_PATTERN,
    RULE_DESCRIPTION_TOO_LONG,
    RULE_ADDITIONAL_PROPERTIES_OPEN,
)
PROTOCOL_RULE_IDS = (
    RULE_REQUIRED_MISSING_PROPERTY,
    RULE_DUPLICATE_TOOL_NAME,
    RULE_EMPTY_ENUM_OR_BAD_DEFAULT,
    RULE_MISSING_INPUT_SCHEMA,
)
ALL_RULE_IDS = PROVIDER_DEPENDENT_RULE_IDS + PROTOCOL_RULE_IDS + (RULE_UNKNOWN_PROVIDER,)


def _finding(rule_id, severity, tool_name, json_pointer, provider, evidence, message) -> dict:
    return {
        "rule_id": rule_id,
        "severity": severity,
        "tool_name": tool_name,
        "json_pointer": json_pointer,
        "provider": provider,
        "evidence": evidence,
        "message": message,
    }


def _input_schema(tool: dict) -> dict | None:
    schema = tool.get("inputSchema")
    return schema if isinstance(schema, dict) else None


# ---------------------------------------------------------------------------
# Provider-dependent rules (1, 2, 3, 4, 6)
# ---------------------------------------------------------------------------


def check_unsupported_keyword(tool: dict, tool_ptr: str, table: ProviderTable) -> list[dict]:
    schema = _input_schema(tool)
    if schema is None:
        return []
    findings = []
    for node_ptr, node, _depth in schemawalk.walk(schema, ptr.join(tool_ptr, "inputSchema")):
        for key in node:
            if key in table.unsupported_keywords:
                findings.append(
                    _finding(
                        RULE_UNSUPPORTED_KEYWORD,
                        "error",
                        tool.get("name"),
                        ptr.join(node_ptr, key),
                        table.key,
                        {"keyword": key},
                        f"keyword '{key}' is not supported by {table.display_name} "
                        f"(table v{table.version}, {table.source})",
                    )
                )
    return findings


def check_nesting_too_deep(tool: dict, tool_ptr: str, table: ProviderTable) -> list[dict]:
    schema = _input_schema(tool)
    if schema is None:
        return []
    violators = [
        (node_ptr, depth)
        for node_ptr, _node, depth in schemawalk.walk(schema, ptr.join(tool_ptr, "inputSchema"))
        if depth > table.max_nesting_depth
    ]
    if not violators:
        return []
    node_ptr, depth = min(violators, key=lambda pair: (pair[1], pair[0]))
    return [
        _finding(
            RULE_NESTING_TOO_DEEP,
            "error",
            tool.get("name"),
            node_ptr,
            table.key,
            {"depth": depth, "max_nesting_depth": table.max_nesting_depth},
            f"schema nests {depth} levels deep, exceeding {table.display_name}'s "
            f"documented max of {table.max_nesting_depth} (table v{table.version})",
        )
    ]


def check_name_pattern(tool: dict, tool_ptr: str, table: ProviderTable) -> list[dict]:
    name = tool.get("name")
    if not isinstance(name, str):
        return []
    findings = []
    if len(name) > table.name_max_len:
        findings.append(
            _finding(
                RULE_NAME_PATTERN,
                "error",
                name,
                ptr.join(tool_ptr, "name"),
                table.key,
                {"length": len(name), "name_max_len": table.name_max_len},
                f"tool name is {len(name)} chars, exceeding {table.display_name}'s "
                f"cap of {table.name_max_len} (table v{table.version})",
            )
        )
    if not table.compiled_name_pattern().match(name):
        findings.append(
            _finding(
                RULE_NAME_PATTERN,
                "error",
                name,
                ptr.join(tool_ptr, "name"),
                table.key,
                {"pattern": table.name_pattern},
                f"tool name does not match {table.display_name}'s required pattern "
                f"{table.name_pattern!r} (table v{table.version})",
            )
        )
    return findings


def check_description_too_long(tool: dict, tool_ptr: str, table: ProviderTable) -> list[dict]:
    description = tool.get("description")
    if not isinstance(description, str):
        return []
    if len(description) <= table.description_max_len:
        return []
    return [
        _finding(
            RULE_DESCRIPTION_TOO_LONG,
            "error",
            tool.get("name"),
            ptr.join(tool_ptr, "description"),
            table.key,
            {"length": len(description), "description_max_len": table.description_max_len},
            f"description is {len(description)} chars, exceeding {table.display_name}'s "
            f"cap of {table.description_max_len} (table v{table.version})",
        )
    ]


def check_additional_properties_open(tool: dict, tool_ptr: str, table: ProviderTable) -> list[dict]:
    if table.additional_properties_default != "open":
        return []
    if "additionalProperties" in table.unsupported_keywords:
        # The provider has no mechanism to close an object schema at all --
        # setting the keyword would itself be flagged by rule 1
        # (unsupported-keyword). Asking for a fix that rule 1 would then
        # reject is incoherent, so this rule does not apply to such a
        # provider; the structural "always open" limitation is inherent to
        # the provider, not a fixable per-schema finding.
        return []
    schema = _input_schema(tool)
    if schema is None:
        return []
    findings = []
    for node_ptr, node, _depth in schemawalk.walk(schema, ptr.join(tool_ptr, "inputSchema")):
        if schemawalk.is_object_node(node) and "additionalProperties" not in node:
            findings.append(
                _finding(
                    RULE_ADDITIONAL_PROPERTIES_OPEN,
                    "error",
                    tool.get("name"),
                    node_ptr,
                    table.key,
                    {},
                    f"object schema does not set 'additionalProperties', and "
                    f"{table.display_name} defaults it open (table v{table.version}): "
                    "the model may pass arguments this schema never declared",
                )
            )
    return findings


PROVIDER_DEPENDENT_CHECKS = {
    RULE_UNSUPPORTED_KEYWORD: check_unsupported_keyword,
    RULE_NESTING_TOO_DEEP: check_nesting_too_deep,
    RULE_NAME_PATTERN: check_name_pattern,
    RULE_DESCRIPTION_TOO_LONG: check_description_too_long,
    RULE_ADDITIONAL_PROPERTIES_OPEN: check_additional_properties_open,
}


# ---------------------------------------------------------------------------
# Provider-independent / protocol rules (5, 7, 8, 9)
# ---------------------------------------------------------------------------


def check_required_missing_property(tool: dict, tool_ptr: str) -> list[dict]:
    schema = _input_schema(tool)
    if schema is None:
        return []
    findings = []
    for node_ptr, node, _depth in schemawalk.walk(schema, ptr.join(tool_ptr, "inputSchema")):
        required = node.get("required")
        if not isinstance(required, list):
            continue
        props = node.get("properties")
        props = props if isinstance(props, dict) else {}
        for i, req_name in enumerate(required):
            if req_name not in props:
                findings.append(
                    _finding(
                        RULE_REQUIRED_MISSING_PROPERTY,
                        "error",
                        tool.get("name"),
                        ptr.join(node_ptr, "required", i),
                        PROTOCOL,
                        {"required_name": req_name},
                        f"'{req_name}' is listed in required but absent from properties "
                        "-- this schema can never be satisfied",
                    )
                )
    return findings


def check_duplicate_tool_name(tools: list[dict], tools_root: str) -> list[dict]:
    findings = []
    seen: dict[str, int] = {}
    for idx, tool in enumerate(tools):
        name = tool.get("name")
        if not isinstance(name, str):
            continue
        if name in seen:
            first_idx = seen[name]
            findings.append(
                _finding(
                    RULE_DUPLICATE_TOOL_NAME,
                    "error",
                    name,
                    ptr.join(tools_root, idx, "name"),
                    PROTOCOL,
                    {"duplicate_of_index": first_idx},
                    f"tool name '{name}' duplicates the tool at index {first_idx}; "
                    "one silently shadows the other",
                )
            )
        else:
            seen[name] = idx
    return findings


def check_empty_enum_or_bad_default(tool: dict, tool_ptr: str) -> list[dict]:
    schema = _input_schema(tool)
    if schema is None:
        return []
    findings = []
    for node_ptr, node, _depth in schemawalk.walk(schema, ptr.join(tool_ptr, "inputSchema")):
        enum = node.get("enum")
        if isinstance(enum, list) and len(enum) == 0:
            findings.append(
                _finding(
                    RULE_EMPTY_ENUM_OR_BAD_DEFAULT,
                    "error",
                    tool.get("name"),
                    ptr.join(node_ptr, "enum"),
                    PROTOCOL,
                    {"enum": enum},
                    "enum is empty -- no value can ever satisfy this schema",
                )
            )
        if "default" in node:
            violations = validate_value(node["default"], node)
            if violations:
                findings.append(
                    _finding(
                        RULE_EMPTY_ENUM_OR_BAD_DEFAULT,
                        "error",
                        tool.get("name"),
                        ptr.join(node_ptr, "default"),
                        PROTOCOL,
                        {"violations": violations},
                        "default value violates its own local schema: " + "; ".join(violations),
                    )
                )
    return findings


def check_missing_input_schema(tool: dict, tool_ptr: str) -> list[dict]:
    if "inputSchema" not in tool:
        return [
            _finding(
                RULE_MISSING_INPUT_SCHEMA,
                "error",
                tool.get("name"),
                tool_ptr,
                PROTOCOL,
                {},
                "tool is missing 'inputSchema' entirely",
            )
        ]
    schema = tool["inputSchema"]
    if not isinstance(schema, dict):
        return [
            _finding(
                RULE_MISSING_INPUT_SCHEMA,
                "error",
                tool.get("name"),
                ptr.join(tool_ptr, "inputSchema"),
                PROTOCOL,
                {"actual": type(schema).__name__},
                "'inputSchema' is not a JSON object",
            )
        ]
    declared_type = schema.get("type")
    if declared_type != "object":
        if "type" in schema:
            pointer_to = ptr.join(tool_ptr, "inputSchema", "type")
        else:
            pointer_to = ptr.join(tool_ptr, "inputSchema")
        return [
            _finding(
                RULE_MISSING_INPUT_SCHEMA,
                "error",
                tool.get("name"),
                pointer_to,
                PROTOCOL,
                {"declared_type": declared_type},
                f"'inputSchema.type' must be 'object', got {declared_type!r}",
            )
        ]
    return []


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------


def lint(
    tools: list[dict],
    tools_root: str,
    provider_tables: dict[str, ProviderTable | None],
) -> list[dict]:
    """Run every rule.

    `provider_tables` maps each requested provider *key* to its
    `ProviderTable`, or to `None` if that key is not in the known-providers
    table -- in which case provider-dependent rules emit a single
    `unknown-provider` finding per tool for that key instead of guessing.
    """
    findings: list[dict] = []

    for idx, tool in enumerate(tools):
        tool_ptr = ptr.join(tools_root, idx)

        for provider_key, table in provider_tables.items():
            if table is None:
                findings.append(
                    _finding(
                        RULE_UNKNOWN_PROVIDER,
                        "unknown",
                        tool.get("name"),
                        tool_ptr,
                        provider_key,
                        {},
                        f"provider '{provider_key}' is not in mcpshape's provider table -- "
                        "cannot evaluate keyword support, nesting depth, name/description "
                        "caps, or additionalProperties default for it",
                    )
                )
                continue
            for check in PROVIDER_DEPENDENT_CHECKS.values():
                findings.extend(check(tool, tool_ptr, table))

        findings.extend(check_required_missing_property(tool, tool_ptr))
        findings.extend(check_empty_enum_or_bad_default(tool, tool_ptr))
        findings.extend(check_missing_input_schema(tool, tool_ptr))

    findings.extend(check_duplicate_tool_name(tools, tools_root))

    findings.sort(key=lambda f: (_tool_index(f["json_pointer"], tools_root), f["json_pointer"], f["rule_id"]))
    return findings


def _tool_index(pointer_str: str, tools_root: str) -> int:
    prefix = tools_root + "/"
    if not pointer_str.startswith(prefix):
        return -1
    rest = pointer_str[len(prefix):]
    head = rest.split("/", 1)[0]
    try:
        return int(head)
    except ValueError:
        return -1
